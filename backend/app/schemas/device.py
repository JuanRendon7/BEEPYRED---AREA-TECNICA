"""
Schemas Pydantic v2 para el CRUD de equipos de red.

DeviceCreate — validacion de input en POST /devices
DeviceUpdate — validacion de input en PUT /devices/{id} (todos opcionales)
DeviceRead   — respuesta de la API con todos los campos incluido estado actual

Validacion IP: Pydantic v2 IPvAnyAddress valida IPv4 e IPv6.
El campo ip_address se almacena como string en DB pero se valida aqui.
"""
from datetime import datetime
from typing import Any

from pydantic import BaseModel, IPvAnyAddress, field_validator

from app.models.device import DeviceStatus, DeviceType


class DeviceCreate(BaseModel):
    """Schema para crear un equipo. Todos los campos sin default son requeridos."""

    name: str
    ip_address: str
    device_type: DeviceType
    site: str | None = None
    notes: str | None = None
    # Para ONUs: FK al OLT padre
    parent_device_id: int | None = None
    pon_port: str | None = None

    @field_validator("ip_address")
    @classmethod
    def validate_ip(cls, v: str) -> str:
        """Valida que ip_address sea una IPv4 o IPv6 valida."""
        # IPvAnyAddress lanza ValueError si el formato es invalido
        IPvAnyAddress(v)
        return v

    @field_validator("name")
    @classmethod
    def validate_name_not_empty(cls, v: str) -> str:
        """Nombre no puede ser string vacio o solo espacios."""
        if not v or not v.strip():
            raise ValueError("El nombre del equipo no puede estar vacio")
        return v.strip()


class DeviceUpdate(BaseModel):
    """Schema para actualizar un equipo. Todos los campos son opcionales."""

    name: str | None = None
    ip_address: str | None = None
    device_type: DeviceType | None = None
    site: str | None = None
    notes: str | None = None
    is_active: bool | None = None
    parent_device_id: int | None = None
    pon_port: str | None = None

    @field_validator("ip_address", mode="before")
    @classmethod
    def validate_ip_if_present(cls, v: Any) -> Any:
        """Valida IP solo si fue proporcionada."""
        if v is not None:
            IPvAnyAddress(str(v))
        return v

    @field_validator("name", mode="before")
    @classmethod
    def validate_name_if_present(cls, v: Any) -> Any:
        if v is not None and not str(v).strip():
            raise ValueError("El nombre no puede estar vacio")
        return v


class DeviceRead(BaseModel):
    """Schema de respuesta de la API. Incluye campos calculados por el sistema."""

    model_config = {"from_attributes": True}  # Pydantic v2: permite crear desde ORM

    id: int
    name: str
    ip_address: str
    device_type: DeviceType
    site: str | None
    status: DeviceStatus
    is_active: bool
    consecutive_failures: int
    last_seen_at: datetime | None
    created_at: datetime
    updated_at: datetime
    parent_device_id: int | None
    pon_port: str | None
    notes: str | None
