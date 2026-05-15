"""
Collector SSH para OLTs VSOL GPON.

VSOL-01: Estado ONUs via 'show pon onu state gpon 0/X' en 8 puertos, cada 60s.
VSOL-03: Senal optica via 'show pon optical-info gpon 0/X onu N', cada 300s.
VSOL-04: Circuit breaker Redis prefijo 'vsol:' — 3 fallos SSH = 5 min suspension.
VSOL-05: Una sola sesion SSH por ciclo de poll (OLT limita a 3 sesiones concurrentes).
"""
import asyncio
import logging
from datetime import datetime, timezone

import asyncssh
import redis.asyncio as aioredis
from celery import shared_task
from sqlalchemy import select

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.security import decrypt_credential
from app.models.device import Device, DeviceStatus, DeviceType
from app.models.device_credential import DeviceCredential
from app.models.onu import ONU
from app.services.vsol_circuit_breaker import (
    is_vsol_circuit_open,
    record_vsol_failure,
    record_vsol_success,
)
from app.collectors.vsol_parser import parse_optical_info, parse_onu_state
from app.services.telegram import send_telegram_alert

logger = logging.getLogger(__name__)

VSOL_PORTS: int = 8
SIGNAL_ALERT_TTL: int = 3600  # 1 hora — evita spam de alertas repetidas (ALERT-04)

_ONU_STATE_MAP = {
    "ONLINE": DeviceStatus.UP,
    "OFFLINE": DeviceStatus.DOWN,
    "RANGING": DeviceStatus.WARNING,
}


# ---------------------------------------------------------------------------
# Celery tasks — state polling (VSOL-01, cada 60s)
# ---------------------------------------------------------------------------

@shared_task(name="tasks.poll_all_vsol_olts_state")
def poll_all_vsol_olts_state() -> dict:
    return asyncio.run(_poll_all_vsol_olts_state_async())


@shared_task(name="tasks.poll_vsol_olt_state")
def poll_vsol_olt_state(device_id: int) -> dict:
    return asyncio.run(_collect_state_async(device_id))


# ---------------------------------------------------------------------------
# Celery tasks — optical polling (VSOL-03, cada 300s)
# ---------------------------------------------------------------------------

@shared_task(name="tasks.poll_all_vsol_olts_optical")
def poll_all_vsol_olts_optical() -> dict:
    return asyncio.run(_poll_all_vsol_olts_optical_async())


@shared_task(name="tasks.poll_vsol_olt_optical")
def poll_vsol_olt_optical(device_id: int) -> dict:
    return asyncio.run(_collect_optical_async(device_id))


# ---------------------------------------------------------------------------
# Orchestrators
# ---------------------------------------------------------------------------

async def _poll_all_vsol_olts_state_async() -> dict:
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Device)
            .where(Device.is_active.is_(True))
            .where(Device.device_type == DeviceType.OLT_VSOL_GPON)
        )
        devices = list(result.scalars().all())

    if not devices:
        return {"queued": 0}

    for device in devices:
        poll_vsol_olt_state.delay(device.id)

    return {"queued": len(devices)}


async def _poll_all_vsol_olts_optical_async() -> dict:
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Device)
            .where(Device.is_active.is_(True))
            .where(Device.device_type == DeviceType.OLT_VSOL_GPON)
        )
        devices = list(result.scalars().all())

    if not devices:
        return {"queued": 0}

    for device in devices:
        poll_vsol_olt_optical.delay(device.id)

    return {"queued": len(devices)}


# ---------------------------------------------------------------------------
# State collector — VSOL-01
# ---------------------------------------------------------------------------

async def _collect_state_async(device_id: int) -> dict:
    redis_client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    try:
        if await is_vsol_circuit_open(redis_client, device_id):
            logger.info("device %s: vsol circuit open, skipping state poll", device_id)
            return {"skipped": True, "reason": "circuit_open", "device_id": device_id}

        async with AsyncSessionLocal() as db:
            dev_result = await db.execute(select(Device).where(Device.id == device_id))
            device = dev_result.scalar_one_or_none()
            if device is None or device.device_type != DeviceType.OLT_VSOL_GPON:
                return {"skipped": True, "reason": "not_vsol_olt", "device_id": device_id}

            cred_result = await db.execute(
                select(DeviceCredential)
                .where(DeviceCredential.device_id == device_id)
                .where(DeviceCredential.credential_type == "ssh")
                .limit(1)
            )
            cred = cred_result.scalar_one_or_none()
            if cred is None:
                logger.warning("device %s: no ssh credential found", device_id)
                return {"skipped": True, "reason": "no_credential", "device_id": device_id}

            username = cred.username
            password = decrypt_credential(cred.encrypted_password)
            ip = device.ip_address

        total_onus = 0
        try:
            async with asyncssh.connect(
                ip,
                username=username,
                password=password,
                known_hosts=None,
                connect_timeout=settings.VSOL_SSH_TIMEOUT,
                login_timeout=settings.VSOL_SSH_TIMEOUT,
            ) as conn:
                for port in range(VSOL_PORTS):
                    cmd = f"show pon onu state gpon 0/{port}"
                    run_result = await conn.run(cmd, check=False)
                    onus = parse_onu_state(run_result.stdout or "", port=port)
                    for onu_data in onus:
                        async with AsyncSessionLocal() as db:
                            await upsert_onu(
                                db,
                                olt_id=device_id,
                                port=onu_data["port"],
                                onu_index=onu_data["onu_index"],
                                serial_number=onu_data["serial_number"],
                                state=onu_data["state"],
                            )
                        total_onus += 1

            await record_vsol_success(redis_client, device_id)
            return {"collected": True, "device_id": device_id, "onus_processed": total_onus}

        except (asyncssh.Error, OSError) as exc:
            logger.error("device %s: SSH error: %s", device_id, exc)
            just_opened = await record_vsol_failure(redis_client, device_id)
            if just_opened:
                logger.warning("device %s: vsol circuit breaker opened", device_id)
            return {"collected": False, "device_id": device_id}

    finally:
        await redis_client.aclose()


# ---------------------------------------------------------------------------
# Optical collector — VSOL-03
# ---------------------------------------------------------------------------

async def _collect_optical_async(device_id: int) -> dict:
    redis_client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    try:
        if await is_vsol_circuit_open(redis_client, device_id):
            logger.info("device %s: vsol circuit open, skipping optical poll", device_id)
            return {"skipped": True, "reason": "circuit_open", "device_id": device_id}

        async with AsyncSessionLocal() as db:
            dev_result = await db.execute(select(Device).where(Device.id == device_id))
            device = dev_result.scalar_one_or_none()
            if device is None or device.device_type != DeviceType.OLT_VSOL_GPON:
                return {"skipped": True, "reason": "not_vsol_olt", "device_id": device_id}

            cred_result = await db.execute(
                select(DeviceCredential)
                .where(DeviceCredential.device_id == device_id)
                .where(DeviceCredential.credential_type == "ssh")
                .limit(1)
            )
            cred = cred_result.scalar_one_or_none()
            if cred is None:
                return {"skipped": True, "reason": "no_credential", "device_id": device_id}

            username = cred.username
            password = decrypt_credential(cred.encrypted_password)
            ip = device.ip_address
            olt_name = device.name

            onu_result = await db.execute(
                select(ONU)
                .where(ONU.olt_id == device_id)
                .where(ONU.onu_status == "ONLINE")
            )
            online_onus = list(onu_result.scalars().all())

        if not online_onus:
            return {"collected": True, "device_id": device_id, "onus_polled": 0}

        updated = 0
        try:
            async with asyncssh.connect(
                ip,
                username=username,
                password=password,
                known_hosts=None,
                connect_timeout=settings.VSOL_SSH_TIMEOUT,
                login_timeout=settings.VSOL_SSH_TIMEOUT,
            ) as conn:
                for onu in online_onus:
                    if onu.onu_index is None or onu.pon_port is None:
                        continue
                    cmd = f"show pon optical-info {onu.pon_port} onu {onu.onu_index}"
                    run_result = await conn.run(cmd, check=False)
                    optical = parse_optical_info(run_result.stdout or "")
                    if optical:
                        async with AsyncSessionLocal() as db:
                            res = await db.execute(select(ONU).where(ONU.id == onu.id))
                            fresh_onu = res.scalar_one_or_none()
                            if fresh_onu:
                                if "signal_rx_dbm" in optical:
                                    fresh_onu.signal_rx_dbm = optical["signal_rx_dbm"]
                                if "signal_tx_dbm" in optical:
                                    fresh_onu.signal_tx_dbm = optical["signal_tx_dbm"]
                                fresh_onu.last_updated_at = datetime.now(timezone.utc)
                                await db.commit()
                        if "signal_rx_dbm" in optical:
                            await _check_signal_alert(
                                redis_client,
                                onu_id=onu.id,
                                serial_number=onu.serial_number,
                                signal_rx_dbm=optical["signal_rx_dbm"],
                                olt_name=olt_name,
                            )
                        updated += 1

            await record_vsol_success(redis_client, device_id)
            return {"collected": True, "device_id": device_id, "onus_polled": updated}

        except (asyncssh.Error, OSError) as exc:
            logger.error("device %s: optical SSH error: %s", device_id, exc)
            just_opened = await record_vsol_failure(redis_client, device_id)
            if just_opened:
                logger.warning("device %s: vsol circuit breaker opened (optical)", device_id)
            return {"collected": False, "device_id": device_id}

    finally:
        await redis_client.aclose()


# ---------------------------------------------------------------------------
# upsert_onu — helper para crear/actualizar Device + ONU
# ---------------------------------------------------------------------------

async def upsert_onu(
    db,
    olt_id: int,
    port: int,
    onu_index: int,
    serial_number: str,
    state: str,
) -> None:
    """
    Inserta o actualiza ONU en tables devices + onus.

    ip_address="0.0.0.0" porque las ONUs no tienen IP asignable.
    Device.status se mapea desde el estado GPON: ONLINE→UP, OFFLINE→DOWN, RANGING→WARNING.
    """
    pon_port_str = f"0/{port}"
    dev_status = _ONU_STATE_MAP.get(state, DeviceStatus.UNKNOWN)
    now = datetime.now(timezone.utc)

    result = await db.execute(
        select(ONU)
        .where(ONU.olt_id == olt_id)
        .where(ONU.serial_number == serial_number)
    )
    existing_onu = result.scalar_one_or_none()

    if existing_onu is None:
        new_device = Device(
            name=f"ONU-{serial_number}",
            ip_address="0.0.0.0",
            device_type=DeviceType.ONU,
            status=dev_status,
            is_active=True,
            parent_device_id=olt_id,
            pon_port=pon_port_str,
        )
        db.add(new_device)
        await db.flush()

        new_onu = ONU(
            device_id=new_device.id,
            olt_id=olt_id,
            serial_number=serial_number,
            pon_port=pon_port_str,
            onu_index=onu_index,
            onu_status=state,
            last_updated_at=now,
        )
        db.add(new_onu)
    else:
        existing_onu.onu_status = state
        existing_onu.onu_index = onu_index
        existing_onu.last_updated_at = now

        dev_result = await db.execute(select(Device).where(Device.id == existing_onu.device_id))
        dev = dev_result.scalar_one_or_none()
        if dev:
            dev.status = dev_status
            if state == "ONLINE":
                dev.last_seen_at = now

    await db.commit()


# ---------------------------------------------------------------------------
# Alerta señal optica baja — VSOL-03/ALERT
# ---------------------------------------------------------------------------

async def _check_signal_alert(
    redis_client,
    onu_id: int,
    serial_number: str | None,
    signal_rx_dbm: float,
    olt_name: str,
) -> None:
    """
    Envia alerta Telegram si señal Rx < ONU_SIGNAL_MIN_DBM.
    Debounce via Redis TTL SIGNAL_ALERT_TTL — evita spam de alertas repetidas.
    """
    if signal_rx_dbm >= settings.ONU_SIGNAL_MIN_DBM:
        return

    alert_key = f"vsol:signal_alert:{onu_id}"
    if await redis_client.exists(alert_key):
        return

    text = (
        f"⚠️ <b>SEÑAL BAJA ONU</b>\n"
        f"<b>Serial:</b> <code>{serial_number or 'N/A'}</code>\n"
        f"<b>Rx:</b> {signal_rx_dbm:.2f} dBm (umbral: {settings.ONU_SIGNAL_MIN_DBM} dBm)\n"
        f"<b>OLT:</b> {olt_name}"
    )
    await send_telegram_alert(text)
    await redis_client.setex(alert_key, SIGNAL_ALERT_TTL, "1")
