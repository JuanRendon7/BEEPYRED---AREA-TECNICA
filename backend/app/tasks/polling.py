"""
Worker de ICMP polling para BEEPYRED NOC.

POLL-01: Ejecuta ping ICMP a todos los equipos activos cada 60s via Celery beat.
POLL-02: asyncio.Semaphore(50) limita concurrencia maxima — no satura la red.
POLL-03: DOWN solo tras CONSECUTIVE_FAILURES_THRESHOLD fallos consecutivos (debounce).
POLL-04: Cambios de estado publicados a Redis canal 'device_status' para SSE.
POLL-05: asyncio.wait_for(timeout=DEVICE_TIMEOUT_SECONDS) aisla fallos individuales.

CRITICO — iputils-ping en Dockerfile:
    El stage 'base' del Dockerfile ya tiene:
    RUN apt-get install -y iputils-ping
    iputils-ping moderno usa ICMP datagram socket (no NET_RAW) — funciona en Railway.

CRITICO — Celery + asyncio:
    El task Celery es sincronico; asyncio.run() crea un event loop limpio por invocacion.
    NO usar loop.run_until_complete() — deprecated en Python 3.10+.
"""
import asyncio
import json
from datetime import datetime, timezone

import redis.asyncio as aioredis
from celery import shared_task
from sqlalchemy import select

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.models.device import Device, DeviceStatus

# Semaforo global por proceso — MAX_CONCURRENT_CONNECTIONS=50
# Nota: es por-proceso Celery; con concurrency=1 en polling worker no hay doble conteo
_semaphore = asyncio.Semaphore(settings.MAX_CONCURRENT_CONNECTIONS)


# ---------------------------------------------------------------------------
# Tarea principal Celery (sincronico — Celery no entiende async nativo)
# ---------------------------------------------------------------------------

@shared_task(name="tasks.poll_all_devices")
def poll_all_devices() -> dict:
    """
    POLL-01: Task Celery que ejecuta el ciclo completo de ping ICMP.
    Registrado en celery beat como tarea periodica cada POLL_INTERVAL_SECONDS.
    Retorna resumen {polled, up, down, errors} para logging.
    """
    return asyncio.run(_poll_all_devices_async())


# ---------------------------------------------------------------------------
# Implementacion async interna
# ---------------------------------------------------------------------------

async def _poll_all_devices_async() -> dict:
    """Obtiene lista de dispositivos activos y ejecuta ping concurrente."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Device).where(Device.is_active == True)  # noqa: E712
        )
        devices = list(result.scalars().all())

    if not devices:
        return {"polled": 0, "up": 0, "down": 0, "errors": 0}

    # Ejecutar pings concurrentes con return_exceptions=True para no propagar errores
    results = await asyncio.gather(
        *[_ping_and_update(device) for device in devices],
        return_exceptions=True,
    )

    up_count = sum(1 for r in results if r is True)
    down_count = sum(1 for r in results if r is False)
    error_count = sum(1 for r in results if isinstance(r, Exception))

    return {
        "polled": len(devices),
        "up": up_count,
        "down": down_count,
        "errors": error_count,
    }


async def ping_host(ip: str, timeout: int | None = None) -> bool:
    """
    POLL-05: Ejecuta ping ICMP a la IP dada usando subprocess iputils-ping.

    Usa asyncio.Semaphore(_semaphore) para limitar concurrencia (POLL-02).
    Usa asyncio.wait_for para timeout individual — no bloquea el ciclo (POLL-05).

    Retorna:
        True  — host responde al ping (returncode 0)
        False — host no responde, timeout, o error de red

    CRITICO: iputils-ping moderno usa ICMP datagram socket (no NET_RAW).
    Railway no da NET_RAW — subprocess es la unica forma funcional.
    """
    if timeout is None:
        timeout = settings.DEVICE_TIMEOUT_SECONDS

    async with _semaphore:
        proc = None
        try:
            proc = await asyncio.create_subprocess_exec(
                "ping",
                "-c", "1",          # un solo ping
                "-W", str(timeout), # timeout en segundos para iputils-ping
                ip,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            # wait_for con timeout + 1 para dar margen al proceso antes de matar
            await asyncio.wait_for(proc.wait(), timeout=float(timeout + 1))
            return proc.returncode == 0
        except (asyncio.TimeoutError, OSError):
            if proc is not None:
                try:
                    proc.kill()
                except ProcessLookupError:
                    pass  # proceso ya termino
            return False


async def publish_status_update(device_id: int, new_status: str) -> None:
    """
    POLL-04: Publica cambio de estado a Redis canal 'device_status' para SSE.

    El endpoint SSE en Plan 04 suscribe a este canal y empuja el evento al browser.
    Formato del mensaje: {"id": <device_id>, "status": "<status_value>"}
    """
    r = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    try:
        payload = json.dumps({"id": device_id, "status": new_status})
        await r.publish("device_status", payload)
    finally:
        await r.aclose()


async def _ping_and_update(device: Device) -> bool:
    """
    Pinga un dispositivo y actualiza su estado en DB.

    Logica POLL-03 — debounce anti-falsos-positivos:
    - Exito: consecutive_failures = 0, status = UP, last_seen_at = ahora
    - Fallo: consecutive_failures += 1
      - Si consecutive_failures >= CONSECUTIVE_FAILURES_THRESHOLD: status = DOWN
      - Si aun no llego al threshold: status no cambia (puede seguir UP)

    Publica a Redis SOLO cuando el status cambia (no en cada poll).
    """
    is_up = await ping_host(device.ip_address)
    previous_status = device.status

    async with AsyncSessionLocal() as db:
        # Re-obtener dispositivo con sesion fresca para evitar objetos detached
        result = await db.execute(
            select(Device).where(Device.id == device.id)
        )
        dev = result.scalar_one_or_none()
        if dev is None:
            return is_up  # dispositivo eliminado durante el ciclo

        if is_up:
            dev.consecutive_failures = 0
            dev.status = DeviceStatus.UP
            dev.last_seen_at = datetime.now(timezone.utc)
        else:
            dev.consecutive_failures += 1
            if dev.consecutive_failures >= settings.CONSECUTIVE_FAILURES_THRESHOLD:
                dev.status = DeviceStatus.DOWN
            # Si consecutive_failures < threshold, el status permanece igual

        new_status = dev.status
        await db.commit()

    # Publicar a Redis solo si el status cambio
    if new_status != previous_status:
        await publish_status_update(device.id, new_status.value)

    return is_up
