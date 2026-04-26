from datetime import datetime
from sqlalchemy import Integer, ForeignKey, DateTime, Text, Boolean
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base


class Incident(Base):
    """Registro de incidentes: equipo DOWN y recuperacion UP."""
    __tablename__ = "incidents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("devices.id", ondelete="CASCADE"), nullable=False
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Duracion en segundos — calculada al cerrar el incidente (resolved_at - started_at)
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cause: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Flags para no enviar alertas Telegram duplicadas
    alert_sent: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    recovery_alert_sent: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
