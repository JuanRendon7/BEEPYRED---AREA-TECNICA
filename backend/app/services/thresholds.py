"""
Servicio de umbrales de alerta configurables (MK-04, ALERT-05, ALERT-06).

Orden de precedencia:
  1. Umbral especifico por device_id en tabla alerts
  2. Umbral global (device_id IS NULL) en tabla alerts
  3. Variable de entorno en settings (fallback)
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.alert import Alert


async def get_threshold(
    db: AsyncSession,
    alert_type: str,
    device_id: int | None = None,
) -> float | None:
    """
    Retorna el umbral activo para alert_type.
    device_id=None busca solo umbral global + env var fallback.
    """
    # 1. Umbral especifico por dispositivo
    if device_id is not None:
        result = await db.execute(
            select(Alert.threshold_value)
            .where(Alert.device_id == device_id)
            .where(Alert.alert_type == alert_type)
            .where(Alert.is_active.is_(True))
            .limit(1)
        )
        row = result.scalar_one_or_none()
        if row is not None:
            return float(row)

    # 2. Umbral global (device_id IS NULL)
    result = await db.execute(
        select(Alert.threshold_value)
        .where(Alert.device_id.is_(None))
        .where(Alert.alert_type == alert_type)
        .where(Alert.is_active.is_(True))
        .limit(1)
    )
    row = result.scalar_one_or_none()
    if row is not None:
        return float(row)

    # 3. Fallback a env var
    _defaults: dict[str, float] = {
        "cpu_high": settings.CPU_ALERT_THRESHOLD_PCT,
        "signal_low": settings.ONU_SIGNAL_MIN_DBM,
    }
    return _defaults.get(alert_type)
