"""
Schemas Pydantic v2 para el endpoint de incidentes.
INC-03: IncidentResponse incluye campos de Device via JOIN.
"""
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class IncidentResponse(BaseModel):
    """
    Schema de respuesta para GET /incidents.
    Los campos device_name y device_site vienen del JOIN con la tabla devices.
    """
    model_config = ConfigDict(from_attributes=True)

    id: int
    device_id: int
    device_name: str
    device_site: str | None
    started_at: datetime
    resolved_at: datetime | None
    duration_seconds: int | None
    alert_sent: bool
    recovery_alert_sent: bool
