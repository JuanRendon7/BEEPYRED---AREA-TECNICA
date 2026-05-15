"""Schema Pydantic v2 para el endpoint GET /api/v1/onus."""
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


class ONUResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    device_id: int
    olt_id: int | None
    serial_number: str | None
    pon_port: str | None
    onu_index: int | None
    signal_rx_dbm: Decimal | None
    signal_tx_dbm: Decimal | None
    onu_status: str | None
    last_updated_at: datetime | None
    # Campos del JOIN con tabla devices
    device_name: str | None
    site: str | None
    olt_name: str | None
