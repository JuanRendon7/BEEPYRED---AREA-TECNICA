"""
Tasks Celery para pipeline de alertas y ciclo de vida de incidentes.

ALERT-01: handle_device_down encola con countdown (debounce anti-flapping)
ALERT-04: al ejecutarse, verifica si el incidente sigue abierto
INC-01:   open_incident_if_not_exists — INSERT con SELECT FOR UPDATE
INC-02:   close_incident — UPDATE resolved_at + duration_seconds
ALERT-02: formato DOWN con nombre, IP, sitio, timestamp (via telegram.py)
ALERT-03: formato UP con duracion de la caida (via telegram.py)
ALERT-05: alert_sent / recovery_alert_sent en la fila de incidente

SEGURIDAD:
- T-3-09: SELECT FOR UPDATE en open_incident_if_not_exists y close_incident
  previene race conditions entre workers Celery paralelos.
- T-3-11: device_id siempre validado via SELECT antes de ejecutar logica.
"""
import asyncio
import logging
from datetime import datetime, timezone

from celery import shared_task
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.models.device import Device
from app.models.incident import Incident
from app.services.telegram import (
    format_down_message,
    format_up_message,
    send_telegram_alert,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Celery tasks (sincronicos — mismo patron establecido en polling.py)
# ---------------------------------------------------------------------------

@shared_task(name="tasks.handle_device_down")
def handle_device_down(device_id: int) -> dict:
    """
    ALERT-01/04: Ejecutado con countdown=ALERT_DEBOUNCE_SECONDS desde polling.py.

    Al ejecutarse, verifica si el incidente sigue abierto (anti-flapping ALERT-04).
    Si el equipo se recupero dentro del ventana de debounce, el incidente ya estara
    cerrado y la alerta se suprime.
    """
    return asyncio.run(_handle_device_down_async(device_id))


@shared_task(name="tasks.handle_device_recovery")
def handle_device_recovery(device_id: int) -> dict:
    """
    ALERT-03/INC-02: Ejecutado inmediatamente al detectar transicion DOWN->UP.
    Cierra incidente y envia mensaje Telegram con duracion de la caida.
    """
    return asyncio.run(_handle_device_recovery_async(device_id))


# ---------------------------------------------------------------------------
# Logica async interna
# ---------------------------------------------------------------------------

async def _handle_device_down_async(device_id: int) -> dict:
    """
    Abre incidente en DB y envia alerta Telegram DOWN.

    Debounce ALERT-04: el task se encoló con countdown=N segundos.
    Si el equipo se recupero antes del countdown, cuando este task
    se ejecute, el incidente ya estara cerrado (resolved_at != None) —
    en ese caso no se envia la alerta DOWN.
    """
    async with AsyncSessionLocal() as db:
        # T-3-11: Validar que el device existe antes de ejecutar cualquier logica
        result = await db.execute(
            select(Device).where(Device.id == device_id)
        )
        device = result.scalar_one_or_none()
        if device is None:
            return {"skipped": True, "reason": "device_not_found"}

        # INC-01: Abrir incidente atomicamente (SELECT FOR UPDATE)
        incident = await open_incident_if_not_exists(db, device_id)

        # ALERT-04 Debounce: si el incidente ya fue cerrado (equipo recupero antes
        # del countdown), no enviar la alerta DOWN
        if incident.resolved_at is not None:
            logger.info(
                "device %s: recovered before debounce window, suppressing DOWN alert",
                device_id,
            )
            return {"skipped": True, "reason": "recovered_before_debounce"}

        # No enviar doble alerta si ya fue enviada
        if incident.alert_sent:
            return {"skipped": True, "reason": "alert_already_sent"}

        # ALERT-02: Formatear y enviar mensaje Telegram DOWN
        text = format_down_message(
            device_name=device.name,
            ip=device.ip_address,
            site=device.site,
            timestamp=incident.started_at,
        )
        await send_telegram_alert(text)

        # ALERT-05: Marcar alerta enviada
        incident.alert_sent = True
        await db.commit()

    logger.info("device %s: DOWN alert sent, incident opened", device_id)
    return {"alerted": True, "device_id": device_id, "incident_id": incident.id}


async def _handle_device_recovery_async(device_id: int) -> dict:
    """
    Cierra incidente abierto y envia alerta Telegram UP con duracion.
    """
    async with AsyncSessionLocal() as db:
        # T-3-11: Validar que el device existe
        result = await db.execute(
            select(Device).where(Device.id == device_id)
        )
        device = result.scalar_one_or_none()
        if device is None:
            return {"skipped": True, "reason": "device_not_found"}

        # INC-02: Cerrar incidente atomicamente (SELECT FOR UPDATE)
        incident = await close_incident(db, device_id)
        if incident is None:
            # No habia incidente abierto — recovery sin DOWN registrado
            logger.info(
                "device %s: recovery without open incident, skipping", device_id
            )
            return {"skipped": True, "reason": "no_open_incident"}

        duration = incident.duration_seconds or 0

        # No enviar doble alerta de recovery
        if incident.recovery_alert_sent:
            return {"skipped": True, "reason": "recovery_alert_already_sent"}

        # ALERT-03: Formatear y enviar mensaje Telegram UP
        text = format_up_message(
            device_name=device.name,
            ip=device.ip_address,
            site=device.site,
            duration_seconds=duration,
        )
        await send_telegram_alert(text)

        # ALERT-05: Marcar recovery alert enviada
        incident.recovery_alert_sent = True
        await db.commit()

    logger.info(
        "device %s: UP alert sent, incident closed (duration: %ss)",
        device_id, duration,
    )
    return {"alerted": True, "device_id": device_id, "duration_seconds": duration}


# ---------------------------------------------------------------------------
# Helpers de incidentes (INC-01, INC-02)
# ---------------------------------------------------------------------------

async def open_incident_if_not_exists(
    db: AsyncSession,
    device_id: int,
) -> Incident:
    """
    INC-01: Abre un incidente si no hay uno abierto para el dispositivo.

    Usa SELECT FOR UPDATE (T-3-09) para evitar race conditions entre workers
    Celery que procesan el mismo dispositivo en paralelo.
    Retorna el incidente abierto (nuevo o existente).
    """
    result = await db.execute(
        select(Incident)
        .where(Incident.device_id == device_id)
        .where(Incident.resolved_at.is_(None))
        .order_by(Incident.started_at.desc())
        .limit(1)
        .with_for_update()
    )
    existing = result.scalar_one_or_none()
    if existing is not None:
        return existing

    new_incident = Incident(
        device_id=device_id,
        started_at=datetime.now(timezone.utc),
        alert_sent=False,
        recovery_alert_sent=False,
    )
    db.add(new_incident)
    await db.flush()  # obtener ID asignado antes del commit
    return new_incident


async def close_incident(
    db: AsyncSession,
    device_id: int,
) -> Incident | None:
    """
    INC-02: Cierra el incidente abierto mas reciente del dispositivo.

    Calcula duration_seconds = resolved_at - started_at.
    Usa SELECT FOR UPDATE (T-3-09) para evitar doble cierre concurrente.
    Retorna None si no habia incidente abierto.

    Nota: no hace commit aqui — el caller hace commit despues de marcar
    recovery_alert_sent para que ambos cambios queden en la misma transaccion.
    """
    result = await db.execute(
        select(Incident)
        .where(Incident.device_id == device_id)
        .where(Incident.resolved_at.is_(None))
        .order_by(Incident.started_at.desc())
        .limit(1)
        .with_for_update()
    )
    incident = result.scalar_one_or_none()
    if incident is None:
        return None

    now = datetime.now(timezone.utc)
    incident.resolved_at = now
    incident.duration_seconds = int((now - incident.started_at).total_seconds())
    return incident
