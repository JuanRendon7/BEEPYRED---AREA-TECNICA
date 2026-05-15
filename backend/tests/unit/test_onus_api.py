"""
Tests del endpoint GET /api/v1/onus — VSOL-01/03.

Cubre:
- 200 con lista de ONUs y campos del JOIN (device_name, site, olt_name)
- 401 sin JWT
- Filtros site, state y olt_id devuelven 200
- Paginacion limit/offset
- Todos los campos del schema ONUResponse presentes
"""
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_onu_row(
    id=1,
    device_id=10,
    olt_id=1,
    serial_number="4857454c12345601",
    pon_port="0/1",
    onu_index=1,
    signal_rx_dbm=Decimal("-19.47"),
    signal_tx_dbm=Decimal("2.00"),
    onu_status="ONLINE",
    last_updated_at=None,
    device_name="ONU-4857454c12345601",
    site="San Luis",
    olt_name="BeepyRed_OLT_GPON_SanLuis",
):
    """Simula un RowMapping de SQLAlchemy del JOIN ONU → Device → OLT."""
    data = {
        "id": id,
        "device_id": device_id,
        "olt_id": olt_id,
        "serial_number": serial_number,
        "pon_port": pon_port,
        "onu_index": onu_index,
        "signal_rx_dbm": signal_rx_dbm,
        "signal_tx_dbm": signal_tx_dbm,
        "onu_status": onu_status,
        "last_updated_at": last_updated_at or datetime(2026, 5, 14, 10, 0, 0, tzinfo=timezone.utc),
        "device_name": device_name,
        "site": site,
        "olt_name": olt_name,
    }
    row = MagicMock()
    row.keys = MagicMock(return_value=list(data.keys()))
    row.__iter__ = MagicMock(return_value=iter(data.items()))
    row.__getitem__ = MagicMock(side_effect=lambda k: data[k])
    return row


def _make_mock_db(rows=None):
    """Mock de AsyncSession para el endpoint de ONUs."""
    if rows is None:
        rows = []
    mock_mappings = MagicMock()
    mock_mappings.all.return_value = rows

    mock_result = MagicMock()
    mock_result.mappings.return_value = mock_mappings

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=mock_result)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    async def override_get_db():
        yield mock_session

    return override_get_db, mock_session


def _make_test_app(db_override, authenticated=True):
    from app.main import app
    from app.core.database import get_db
    from app.core.auth import get_current_active_user

    app.dependency_overrides[get_db] = db_override

    if authenticated:
        mock_user = MagicMock()
        mock_user.username = "admin"
        async def override_user():
            return mock_user
        app.dependency_overrides[get_current_active_user] = override_user
    else:
        app.dependency_overrides.pop(get_current_active_user, None)

    return app


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_onus_returns_200_with_list(set_test_env_vars):
    """GET /api/v1/onus retorna 200 con lista de ONUs."""
    row = _make_onu_row()
    db_override, _ = _make_mock_db(rows=[row])
    app = _make_test_app(db_override)
    client = TestClient(app)

    response = client.get("/api/v1/onus")

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 1
    app.dependency_overrides.clear()


def test_onus_returns_required_fields(set_test_env_vars):
    """ONUResponse incluye id, serial_number, onu_status, device_name, olt_name, site."""
    row = _make_onu_row(
        id=5,
        serial_number="ABCDEF1234567890",
        onu_status="OFFLINE",
        device_name="ONU-ABCDEF",
        site="Vereda Sur",
        olt_name="BeepyRed_OLT_GPON_SanLuis",
    )
    db_override, _ = _make_mock_db(rows=[row])
    app = _make_test_app(db_override)
    client = TestClient(app)

    response = client.get("/api/v1/onus")
    data = response.json()[0]

    assert data["id"] == 5
    assert data["serial_number"] == "ABCDEF1234567890"
    assert data["onu_status"] == "OFFLINE"
    assert data["device_name"] == "ONU-ABCDEF"
    assert data["site"] == "Vereda Sur"
    assert data["olt_name"] == "BeepyRed_OLT_GPON_SanLuis"
    app.dependency_overrides.clear()


def test_onus_returns_signal_dbm_fields(set_test_env_vars):
    """ONUResponse incluye signal_rx_dbm y signal_tx_dbm."""
    row = _make_onu_row(
        signal_rx_dbm=Decimal("-19.47"),
        signal_tx_dbm=Decimal("2.00"),
    )
    db_override, _ = _make_mock_db(rows=[row])
    app = _make_test_app(db_override)
    client = TestClient(app)

    response = client.get("/api/v1/onus")
    data = response.json()[0]

    assert "signal_rx_dbm" in data
    assert "signal_tx_dbm" in data
    assert float(data["signal_rx_dbm"]) == pytest.approx(-19.47)
    app.dependency_overrides.clear()


def test_onus_returns_empty_list_when_no_onus(set_test_env_vars):
    """Sin ONUs en DB → lista vacia."""
    db_override, _ = _make_mock_db(rows=[])
    app = _make_test_app(db_override)
    client = TestClient(app)

    response = client.get("/api/v1/onus")

    assert response.status_code == 200
    assert response.json() == []
    app.dependency_overrides.clear()


def test_onus_requires_authentication(set_test_env_vars):
    """GET /api/v1/onus retorna 401 sin JWT."""
    db_override, _ = _make_mock_db(rows=[])
    app = _make_test_app(db_override, authenticated=False)
    client = TestClient(app, raise_server_exceptions=False)

    response = client.get("/api/v1/onus")

    assert response.status_code == 401
    app.dependency_overrides.clear()


def test_onus_accepts_site_filter(set_test_env_vars):
    """Filtro ?site=San+Luis acepta sin error (200)."""
    db_override, _ = _make_mock_db(rows=[])
    app = _make_test_app(db_override)
    client = TestClient(app)

    response = client.get("/api/v1/onus?site=San+Luis")

    assert response.status_code == 200
    app.dependency_overrides.clear()


def test_onus_accepts_state_filter(set_test_env_vars):
    """Filtro ?state=ONLINE acepta sin error (200)."""
    db_override, _ = _make_mock_db(rows=[])
    app = _make_test_app(db_override)
    client = TestClient(app)

    response = client.get("/api/v1/onus?state=ONLINE")

    assert response.status_code == 200
    app.dependency_overrides.clear()


def test_onus_accepts_olt_id_filter(set_test_env_vars):
    """Filtro ?olt_id=1 acepta sin error (200)."""
    db_override, _ = _make_mock_db(rows=[])
    app = _make_test_app(db_override)
    client = TestClient(app)

    response = client.get("/api/v1/onus?olt_id=1")

    assert response.status_code == 200
    app.dependency_overrides.clear()


def test_onus_accepts_pagination_params(set_test_env_vars):
    """Parametros limit y offset aceptados sin error."""
    db_override, _ = _make_mock_db(rows=[])
    app = _make_test_app(db_override)
    client = TestClient(app)

    response = client.get("/api/v1/onus?limit=10&offset=20")

    assert response.status_code == 200
    app.dependency_overrides.clear()
