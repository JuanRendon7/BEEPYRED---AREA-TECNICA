from datetime import datetime
from decimal import Decimal
from sqlalchemy import Integer, ForeignKey, String, Numeric, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base


class ONU(Base):
    """ONUs GPON/EPON asociadas a OLTs VSOL."""
    __tablename__ = "onus"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # device_id = la ONU como Device en el inventario
    device_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("devices.id", ondelete="CASCADE"), nullable=False
    )
    # olt_id = la OLT padre (Device de tipo OLT_VSOL_GPON o OLT_VSOL_EPON)
    olt_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("devices.id", ondelete="SET NULL"), nullable=True
    )
    serial_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # Puerto PON: "0/1", "gpon0/1", "epon0/1", etc.
    pon_port: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # Senal optica en dBm — valor tipico GPON Rx: -8 a -27 dBm
    signal_rx_dbm: Mapped[Decimal | None] = mapped_column(Numeric(precision=8, scale=4), nullable=True)
    signal_tx_dbm: Mapped[Decimal | None] = mapped_column(Numeric(precision=8, scale=4), nullable=True)
    # Estados: "ONLINE", "OFFLINE", "RANGING", "UNKNOWN"
    onu_status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    last_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
