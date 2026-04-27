"""
CRUD de equipos de red — INV-01, INV-02, INV-03, INV-04.

Endpoints:
    GET  /devices           — lista todos los activos (filtro ?site=...)
    POST /devices           — crear equipo
    GET  /devices/{id}      — obtener equipo por ID
    PUT  /devices/{id}      — actualizar equipo (campos parciales)
    DELETE /devices/{id}    — eliminar (soft delete: is_active=False)

Todos los endpoints requieren Bearer token valido (AUTH-03).
El estado actual (status) viene de la DB — el worker lo actualiza via polling.
"""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser
from app.core.database import get_db
from app.models.device import Device, DeviceStatus
from app.schemas.device import DeviceCreate, DeviceRead, DeviceUpdate

router = APIRouter(prefix="/devices", tags=["devices"])


@router.get("", response_model=list[DeviceRead])
async def list_devices(
    _: CurrentUser,
    db: AsyncSession = Depends(get_db),
    site: str | None = Query(default=None, description="Filtrar por sitio geografico"),
    active_only: bool = Query(default=True, description="Solo equipos activos"),
) -> list[Device]:
    """
    INV-02, INV-04: Lista equipos con estado actual UP/DOWN/WARNING/UNKNOWN.
    Filtrar por sitio: GET /devices?site=Torre+Norte
    """
    stmt = select(Device)
    if active_only:
        stmt = stmt.where(Device.is_active == True)  # noqa: E712
    if site:
        stmt = stmt.where(Device.site == site)
    stmt = stmt.order_by(Device.site.nulls_last(), Device.name)
    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.post("", response_model=DeviceRead, status_code=status.HTTP_201_CREATED)
async def create_device(
    device_in: DeviceCreate,
    _: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> Device:
    """
    INV-01, INV-03: Registrar nuevo equipo en el inventario.
    El estado inicial es UNKNOWN — el worker lo actualizara en el primer ciclo de polling.
    """
    device = Device(
        name=device_in.name,
        ip_address=device_in.ip_address,
        device_type=device_in.device_type,
        site=device_in.site,
        notes=device_in.notes,
        parent_device_id=device_in.parent_device_id,
        pon_port=device_in.pon_port,
        status=DeviceStatus.UNKNOWN,
        is_active=True,
        consecutive_failures=0,
    )
    db.add(device)
    await db.flush()   # obtener id antes de commit
    await db.refresh(device)
    return device


@router.get("/{device_id}", response_model=DeviceRead)
async def get_device(
    device_id: int,
    _: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> Device:
    """Obtener equipo por ID. Retorna 404 si no existe o esta eliminado."""
    device = await _get_device_or_404(db, device_id)
    return device


@router.put("/{device_id}", response_model=DeviceRead)
async def update_device(
    device_id: int,
    device_in: DeviceUpdate,
    _: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> Device:
    """
    INV-03: Actualizar equipo existente. Solo los campos provistos se modifican.
    No se puede cambiar el status via este endpoint — lo gestiona el worker de polling.
    """
    device = await _get_device_or_404(db, device_id)

    update_data = device_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(device, field, value)

    await db.flush()
    await db.refresh(device)
    return device


@router.delete("/{device_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_device(
    device_id: int,
    _: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> None:
    """
    INV-03: Eliminar equipo del inventario (soft delete — is_active=False).
    El equipo deja de aparecer en listados y el worker deja de poller su IP.
    """
    device = await _get_device_or_404(db, device_id)
    device.is_active = False
    await db.flush()


async def _get_device_or_404(db: AsyncSession, device_id: int) -> Device:
    """Helper interno: obtener device activo por ID o lanzar 404."""
    result = await db.execute(
        select(Device).where(Device.id == device_id, Device.is_active == True)  # noqa: E712
    )
    device = result.scalar_one_or_none()
    if device is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Equipo con id={device_id} no encontrado",
        )
    return device
