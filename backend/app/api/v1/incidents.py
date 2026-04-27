"""
Router FastAPI para historial de incidentes.
INC-03: GET /incidents con filtros opcionales por device_id y site.
Todos los endpoints requieren JWT valido (CurrentUser dependency).
"""
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser
from app.core.database import get_db
from app.models.device import Device
from app.models.incident import Incident
from app.schemas.incident import IncidentResponse

router = APIRouter(prefix="/incidents", tags=["incidents"])


@router.get("", response_model=list[IncidentResponse])
async def list_incidents(
    _: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    device_id: int | None = Query(default=None, description="Filtrar por ID de equipo"),
    site: str | None = Query(default=None, description="Filtrar por sitio geografico"),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[IncidentResponse]:
    """
    Lista incidentes con informacion del equipo afectado.

    Filtros opcionales:
    - device_id: solo incidentes del equipo con ese ID
    - site: solo incidentes de equipos en ese sitio geografico
    - limit/offset: paginacion (default 50, max 500)

    Ordena por started_at DESC (mas reciente primero).
    """
    query = (
        select(
            Incident.id,
            Incident.device_id,
            Device.name.label("device_name"),
            Device.site.label("device_site"),
            Incident.started_at,
            Incident.resolved_at,
            Incident.duration_seconds,
            Incident.alert_sent,
            Incident.recovery_alert_sent,
        )
        .join(Device, Incident.device_id == Device.id)
        .order_by(Incident.started_at.desc())
        .limit(limit)
        .offset(offset)
    )

    if device_id is not None:
        query = query.where(Incident.device_id == device_id)
    if site is not None:
        query = query.where(Device.site == site)

    result = await db.execute(query)
    rows = result.mappings().all()
    return [IncidentResponse.model_validate(dict(row)) for row in rows]
