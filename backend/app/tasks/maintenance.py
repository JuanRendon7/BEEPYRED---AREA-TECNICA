"""
Tarea de mantenimiento: limpieza de datos historicos > 30 dias.

MK-03/INC-04: Celery beat ejecuta esto diariamente a las 3am (hora Colombia).
Usa DELETE SQL directo — mas eficiente que ORM para borrado masivo.

CRITICO: Solo elimina incidentes con resolved_at IS NOT NULL.
Los incidentes abiertos (equipo aun DOWN) nunca se eliminan.
"""
import asyncio
import logging

from celery import shared_task
from sqlalchemy import text

from app.core.database import AsyncSessionLocal

logger = logging.getLogger(__name__)


@shared_task(name="tasks.cleanup_old_data")
def cleanup_old_data() -> dict:
    """
    MK-03/INC-04: Elimina metricas e incidentes con mas de 30 dias.
    Ejecutado por Celery beat diariamente.
    Retorna conteo de filas eliminadas para logging.
    """
    return asyncio.run(_cleanup_async())


async def _cleanup_async() -> dict:
    async with AsyncSessionLocal() as db:
        # MK-03: limpiar metricas > 30 dias
        r_metrics = await db.execute(
            text("DELETE FROM metrics WHERE recorded_at < NOW() - INTERVAL '30 days'")
        )

        # INC-04: limpiar incidentes RESUELTOS > 30 dias
        # CRITICO: WHERE resolved_at IS NOT NULL — no tocar incidentes abiertos
        r_incidents = await db.execute(
            text(
                "DELETE FROM incidents "
                "WHERE resolved_at IS NOT NULL "
                "AND resolved_at < NOW() - INTERVAL '30 days'"
            )
        )

        await db.commit()

    metrics_deleted = r_metrics.rowcount
    incidents_deleted = r_incidents.rowcount

    logger.info(
        "cleanup_old_data: deleted %s metrics rows, %s incident rows",
        metrics_deleted,
        incidents_deleted,
    )
    return {
        "metrics_deleted": metrics_deleted,
        "incidents_deleted": incidents_deleted,
    }
