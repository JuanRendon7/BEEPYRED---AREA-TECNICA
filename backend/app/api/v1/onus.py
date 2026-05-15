"""
Router FastAPI para ONUs GPON/EPON.
GET /api/v1/onus — lista ONUs con filtros opcionales por site, estado y OLT.
Todos los endpoints requieren JWT valido (CurrentUser dependency).
"""
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import aliased
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser
from app.core.database import get_db
from app.models.device import Device
from app.models.onu import ONU
from app.schemas.onu import ONUResponse

router = APIRouter(prefix="/onus", tags=["onus"])

DeviceOnu = aliased(Device, name="device_onu")
DeviceOlt = aliased(Device, name="device_olt")


@router.get("", response_model=list[ONUResponse])
async def list_onus(
    _: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    site: str | None = Query(default=None, description="Filtrar por sitio geografico"),
    state: str | None = Query(default=None, description="Filtrar por estado: ONLINE, OFFLINE, RANGING"),
    olt_id: int | None = Query(default=None, description="Filtrar por ID de OLT"),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> list[ONUResponse]:
    """
    Lista ONUs con informacion del equipo y la OLT padre.

    Filtros opcionales:
    - site: solo ONUs de equipos en ese sitio
    - state: ONLINE | OFFLINE | RANGING
    - olt_id: solo ONUs de esa OLT
    - limit/offset: paginacion (default 100, max 1000)

    Ordena por id ASC.
    """
    query = (
        select(
            ONU.id,
            ONU.device_id,
            ONU.olt_id,
            ONU.serial_number,
            ONU.pon_port,
            ONU.onu_index,
            ONU.signal_rx_dbm,
            ONU.signal_tx_dbm,
            ONU.onu_status,
            ONU.last_updated_at,
            DeviceOnu.name.label("device_name"),
            DeviceOnu.site.label("site"),
            DeviceOlt.name.label("olt_name"),
        )
        .join(DeviceOnu, ONU.device_id == DeviceOnu.id)
        .outerjoin(DeviceOlt, ONU.olt_id == DeviceOlt.id)
        .order_by(ONU.id.asc())
        .limit(limit)
        .offset(offset)
    )

    if site is not None:
        query = query.where(DeviceOnu.site == site)
    if state is not None:
        query = query.where(ONU.onu_status == state)
    if olt_id is not None:
        query = query.where(ONU.olt_id == olt_id)

    result = await db.execute(query)
    rows = result.mappings().all()
    return [ONUResponse.model_validate(dict(row)) for row in rows]
