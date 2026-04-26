import enum
from datetime import datetime
from sqlalchemy import String, Integer, Boolean, DateTime, Text, Enum as SAEnum, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base


class DeviceType(str, enum.Enum):
    MIKROTIK = "mikrotik"
    OLT_VSOL_GPON = "olt_vsol_gpon"
    OLT_VSOL_EPON = "olt_vsol_epon"
    ONU = "onu"
    UBIQUITI = "ubiquiti"
    MIMOSA = "mimosa"
    OTHER = "other"


class DeviceStatus(str, enum.Enum):
    UP = "up"
    DOWN = "down"
    WARNING = "warning"
    UNKNOWN = "unknown"


class Device(Base):
    __tablename__ = "devices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    ip_address: Mapped[str] = mapped_column(String(45), nullable=False)  # IPv4 o IPv6
    device_type: Mapped[DeviceType] = mapped_column(SAEnum(DeviceType, name="devicetype"), nullable=False)
    site: Mapped[str | None] = mapped_column(String(255), nullable=True)   # Torre Norte, Nodo Centro, etc.
    status: Mapped[DeviceStatus] = mapped_column(
        SAEnum(DeviceStatus, name="devicestatus"),
        default=DeviceStatus.UNKNOWN,
        nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Contador de polls fallidos consecutivos — se reinicia a 0 al primer exito
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )
    # Para ONUs: FK al dispositivo OLT padre
    parent_device_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("devices.id", ondelete="SET NULL"), nullable=True
    )
    # Para ONUs: puerto PON asociado ("0/1", "gpon0/1", etc.)
    pon_port: Mapped[str | None] = mapped_column(String(50), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
