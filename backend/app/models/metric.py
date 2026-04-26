from datetime import datetime
from decimal import Decimal
from sqlalchemy import Integer, ForeignKey, DateTime, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base


class Metric(Base):
    """
    Metricas de equipos: CPU %, RAM %, trafico bps, senal dBm, etc.

    DECISION: PostgreSQL puro — sin TimescaleDB. BRIN index en recorded_at
    para queries de series temporales eficientes sin extensiones externas.
    """
    __tablename__ = "metrics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("devices.id", ondelete="CASCADE"), nullable=False
    )
    # Ejemplos: "cpu_pct", "ram_pct", "rx_bps", "tx_bps", "signal_dbm", "rx_signal_dbm"
    metric_name: Mapped[str] = mapped_column(String(100), nullable=False)
    value: Mapped[Decimal] = mapped_column(Numeric(precision=12, scale=4), nullable=False)
    # Ejemplos: "%", "bps", "dBm", "Mbps"
    unit: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # Para metricas por interfaz Mikrotik: nombre de la interfaz
    interface: Mapped[str | None] = mapped_column(String(100), nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )
