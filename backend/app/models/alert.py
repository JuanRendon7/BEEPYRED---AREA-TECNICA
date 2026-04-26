from decimal import Decimal
from sqlalchemy import Integer, ForeignKey, String, Numeric, Boolean
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base


class Alert(Base):
    """Configuracion de umbrales de alerta por equipo o globales."""
    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # device_id NULL = alerta global (aplica a todos los equipos de ese tipo)
    device_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("devices.id", ondelete="CASCADE"), nullable=True
    )
    # Tipos: "cpu_high", "signal_low", "down", "ram_high", "rx_signal_low"
    alert_type: Mapped[str] = mapped_column(String(100), nullable=False)
    threshold_value: Mapped[Decimal | None] = mapped_column(
        Numeric(precision=12, scale=4), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Numero de polls consecutivos que deben superar el umbral antes de alertar
    consecutive_polls_required: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
