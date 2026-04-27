"""
Collector RouterOS API para routers Mikrotik.

MK-01: CPU% y RAM% via /system/resource
MK-02: TX/RX bps por interfaz via /interface
MK-03: api.close() en finally — sin sesiones zombie
MK-04: circuit breaker Redis — is_circuit_open() ANTES de conectar
"""
import asyncio
import logging
from datetime import datetime, timezone

import redis.asyncio as aioredis
from celery import shared_task
from librouteros import async_connect
from sqlalchemy import insert, select

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.security import decrypt_credential
from app.models.device import Device, DeviceType
from app.models.device_credential import DeviceCredential
from app.models.metric import Metric
from app.services.circuit_breaker import (
    is_circuit_open,
    record_api_failure,
    record_api_success,
)

logger = logging.getLogger(__name__)


@shared_task(name="tasks.poll_mikrotik_device")
def poll_mikrotik_device(device_id: int) -> dict:
    """
    MK-01/02: Recolecta metricas CPU, RAM e interfaces de un Mikrotik.
    Llamado por poll_all_mikrotik() para dispositivos de tipo MIKROTIK.
    """
    return asyncio.run(_collect_mikrotik_async(device_id))


@shared_task(name="tasks.poll_all_mikrotik")
def poll_all_mikrotik() -> dict:
    """
    Orquesta el polling de todos los dispositivos Mikrotik activos.
    Encola un poll_mikrotik_device por cada Mikrotik en inventario.
    """
    return asyncio.run(_poll_all_mikrotik_async())


async def _poll_all_mikrotik_async() -> dict:
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Device)
            .where(Device.is_active.is_(True))
            .where(Device.device_type == DeviceType.MIKROTIK)
        )
        devices = list(result.scalars().all())

    if not devices:
        return {"queued": 0}

    for device in devices:
        poll_mikrotik_device.delay(device.id)

    return {"queued": len(devices)}


async def _collect_mikrotik_async(device_id: int) -> dict:
    """Logica async interna del collector Mikrotik."""
    redis_client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    try:
        # MK-04: verificar circuit breaker ANTES de conectar
        if await is_circuit_open(redis_client, device_id):
            logger.info("device %s: circuit open, skipping RouterOS poll", device_id)
            return {"skipped": True, "reason": "circuit_open", "device_id": device_id}

        # Obtener credenciales del dispositivo
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(Device).where(Device.id == device_id)
            )
            device = result.scalar_one_or_none()
            if device is None or device.device_type != DeviceType.MIKROTIK:
                return {"skipped": True, "reason": "not_mikrotik", "device_id": device_id}

            # Obtener credencial RouterOS API
            cred_result = await db.execute(
                select(DeviceCredential)
                .where(DeviceCredential.device_id == device_id)
                .where(DeviceCredential.credential_type == "routeros_api")
                .limit(1)
            )
            cred = cred_result.scalar_one_or_none()
            if cred is None:
                logger.warning("device %s: no routeros_api credential found", device_id)
                return {"skipped": True, "reason": "no_credential", "device_id": device_id}

            username = cred.username
            password = decrypt_credential(cred.encrypted_password)
            ip = device.ip_address

        # Conectar y recolectar
        raw = await _fetch_routeros_data(ip, username, password, device_id, redis_client)
        if raw is None:
            return {"collected": False, "device_id": device_id}

        metrics = _parse_metrics(raw)
        await _write_metrics(device_id, metrics)
        await record_api_success(redis_client, device_id)

        return {"collected": True, "device_id": device_id, "metrics_count": len(metrics)}

    finally:
        await redis_client.aclose()


async def _fetch_routeros_data(
    ip: str,
    username: str,
    password: str,
    device_id: int,
    redis_client: aioredis.Redis,
) -> dict | None:
    """
    Abre conexion RouterOS API, recolecta resource + interfaces, cierra.
    MK-03: api.close() siempre en finally.
    """
    api = None
    try:
        api = await async_connect(
            username=username,
            password=password,
            host=ip,
            port=settings.MIKROTIK_API_PORT,
        )
        # /system/resource — CPU y RAM
        resource_path = api.path("system", "resource")
        resources = [item async for item in resource_path]
        resource = resources[0] if resources else {}

        # /interface — trafico por interfaz
        iface_path = api.path("interface")
        interfaces = [item async for item in iface_path]

        return {"resource": resource, "interfaces": interfaces}

    except Exception as exc:
        logger.error("device %s: RouterOS API error: %s", device_id, exc)
        just_opened = await record_api_failure(redis_client, device_id)
        if just_opened:
            logger.warning(
                "device %s: circuit breaker opened (3 consecutive API failures)",
                device_id,
            )
        return None
    finally:
        if api is not None:
            try:
                api.close()  # MK-03 — cierre explicito, siempre
            except Exception:
                pass  # no propagar errores de cierre


def _parse_metrics(raw: dict) -> list[dict]:
    """
    Convierte la respuesta RouterOS API a lista de dicts para insert(Metric).

    RouterOS 6.x y 7.x usan los mismos nombres de campo en /system/resource.
    Usa .get() defensivo — campos ausentes resultan en metrica omitida (no error).
    """
    metrics: list[dict] = []
    resource = raw.get("resource", {})
    now = datetime.now(timezone.utc)

    # MK-01: CPU% — campo "cpu-load" ya es porcentaje (int 0-100)
    cpu_load = resource.get("cpu-load")
    if cpu_load is not None:
        metrics.append({
            "metric_name": "cpu_pct",
            "value": float(cpu_load),
            "unit": "%",
            "interface": None,
            "recorded_at": now,
        })

    # MK-01: RAM% — calcular desde free-memory y total-memory (bytes)
    free_mem = resource.get("free-memory")
    total_mem = resource.get("total-memory")
    if free_mem is not None and total_mem is not None and int(total_mem) > 0:
        ram_pct = (1.0 - int(free_mem) / int(total_mem)) * 100.0
        metrics.append({
            "metric_name": "ram_pct",
            "value": round(ram_pct, 2),
            "unit": "%",
            "interface": None,
            "recorded_at": now,
        })

    # MK-02: TX/RX bps por interfaz
    for iface in raw.get("interfaces", []):
        iface_name = iface.get("name")
        if not iface_name:
            continue
        tx_bps = iface.get("tx-bits-per-second")
        rx_bps = iface.get("rx-bits-per-second")
        if tx_bps is not None:
            metrics.append({
                "metric_name": "tx_bps",
                "value": float(tx_bps),
                "unit": "bps",
                "interface": iface_name,
                "recorded_at": now,
            })
        if rx_bps is not None:
            metrics.append({
                "metric_name": "rx_bps",
                "value": float(rx_bps),
                "unit": "bps",
                "interface": iface_name,
                "recorded_at": now,
            })

    return metrics


async def _write_metrics(device_id: int, metrics: list[dict]) -> None:
    """
    MK-03: Inserta todas las metricas de un ciclo en una sola transaccion.
    Usa insert(Metric) con lista — SQLAlchemy 2.0 usa executemany via asyncpg.
    """
    if not metrics:
        return
    rows = [{"device_id": device_id, **m} for m in metrics]
    async with AsyncSessionLocal() as db:
        await db.execute(insert(Metric), rows)
        await db.commit()
