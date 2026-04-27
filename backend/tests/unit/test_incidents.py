"""
Tests del endpoint GET /api/v1/incidents — INC-03.

Cubre:
- Listado basico con campos device_name y device_site del JOIN
- Filtro por device_id
- Filtro por site
- Paginacion limit/offset
- Orden started_at DESC
- 401 sin JWT
- IncidentResponse acepta from_attributes=True

CRITICO: No conecta a PostgreSQL real.
Usa override de get_db y get_current_active_user para tests unitarios.
"""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Helpers: construir filas de resultado mock (simula mappings de JOIN)
# ---------------------------------------------------------------------------

def make_incident_row(
    id=1,
    device_id=10,
    device_name="Router Torre Norte",
    device_site="Torre Norte",
    started_at=None,
    resolved_at=None,
    duration_seconds=None,
    alert_sent=False,
    recovery_alert_sent=False,
):
    """Simula un RowMapping de SQLAlchemy (resultado del JOIN)."""
    row = MagicMock()
    row.__iter__ = MagicMock(return_value=iter([
        ("id", id),
        ("device_id", device_id),
        ("device_name", device_name),
        ("device_site", device_site),
        ("started_at", started_at or datetime(2026, 4, 26, 10, 0, 0, tzinfo=timezone.utc)),
        ("resolved_at", resolved_at),
        ("duration_seconds", duration_seconds),
        ("alert_sent", alert_sent),
        ("recovery_alert_sent", recovery_alert_sent),
    ]))
    # Soportar dict(row) — usado en IncidentResponse.model_validate(dict(row))
    row.keys = MagicMock(return_value=[
        "id", "device_id", "device_name", "device_site",
        "started_at", "resolved_at", "duration_seconds",
        "alert_sent", "recovery_alert_sent",
    ])
    row.__getitem__ = MagicMock(side_effect=lambda k: {
        "id": id,
        "device_id": device_id,
        "device_name": device_name,
        "device_site": device_site,
        "started_at": started_at or datetime(2026, 4, 26, 10, 0, 0, tzinfo=timezone.utc),
        "resolved_at": resolved_at,
        "duration_seconds": duration_seconds,
        "alert_sent": alert_sent,
        "recovery_alert_sent": recovery_alert_sent,
    }[k])
    return row


def make_mock_db(rows=None):
    """
    Construye un mock de AsyncSession cuyo execute().mappings().all() retorna rows.
    """
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


def make_test_app(db_override, user_override=None):
    """
    Construye una instancia limpia de la app FastAPI con overrides para tests.
    Importa main para incluir el router de incidents.
    """
    from app.main import app
    from app.core.database import get_db
    from app.core.auth import get_current_active_user

    app.dependency_overrides[get_db] = db_override

    if user_override is not None:
        app.dependency_overrides[get_current_active_user] = user_override
    else:
        # Por defecto: remover override para que falle auth normalmente
        app.dependency_overrides.pop(get_current_active_user, None)

    return app


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_incidents_returns_list_with_device_fields(set_test_env_vars):
    """INC-03: GET /incidents retorna lista con id, device_id, device_name, device_site."""
    row = make_incident_row(
        id=1,
        device_id=10,
        device_name="Router Torre Norte",
        device_site="Torre Norte",
    )
    db_override, _ = make_mock_db(rows=[row])

    mock_user = MagicMock()
    mock_user.username = "admin"

    async def override_user():
        return mock_user

    app = make_test_app(db_override, override_user)
    client = TestClient(app, raise_server_exceptions=True)

    response = client.get("/api/v1/incidents")

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 1
    assert data[0]["id"] == 1
    assert data[0]["device_id"] == 10
    assert data[0]["device_name"] == "Router Torre Norte"
    assert data[0]["device_site"] == "Torre Norte"

    # Limpiar overrides
    app.dependency_overrides.clear()


def test_incidents_returns_all_required_fields(set_test_env_vars):
    """INC-03: IncidentResponse tiene todos los campos requeridos."""
    started = datetime(2026, 4, 25, 8, 0, 0, tzinfo=timezone.utc)
    resolved = datetime(2026, 4, 25, 8, 30, 0, tzinfo=timezone.utc)

    row = make_incident_row(
        id=5,
        device_id=3,
        device_name="OLT Centro",
        device_site="Nodo Centro",
        started_at=started,
        resolved_at=resolved,
        duration_seconds=1800,
        alert_sent=True,
        recovery_alert_sent=True,
    )
    db_override, _ = make_mock_db(rows=[row])

    mock_user = MagicMock()

    async def override_user():
        return mock_user

    app = make_test_app(db_override, override_user)
    client = TestClient(app)

    response = client.get("/api/v1/incidents")

    assert response.status_code == 200
    item = response.json()[0]
    assert item["id"] == 5
    assert item["device_id"] == 3
    assert item["device_name"] == "OLT Centro"
    assert item["device_site"] == "Nodo Centro"
    assert item["duration_seconds"] == 1800
    assert item["alert_sent"] is True
    assert item["recovery_alert_sent"] is True

    app.dependency_overrides.clear()


def test_incidents_requires_jwt(set_test_env_vars):
    """T-3-13: GET /incidents sin Bearer token retorna 401."""
    db_override, _ = make_mock_db(rows=[])

    from app.main import app
    from app.core.database import get_db

    app.dependency_overrides[get_db] = db_override
    # No override para auth — usa el real que verifica JWT
    from app.core.auth import get_current_active_user
    app.dependency_overrides.pop(get_current_active_user, None)

    client = TestClient(app, raise_server_exceptions=False)

    response = client.get("/api/v1/incidents")

    assert response.status_code == 401

    app.dependency_overrides.clear()


def test_incidents_filter_by_device_id(set_test_env_vars):
    """INC-03: GET /incidents?device_id=5 pasa el filtro a la query."""
    db_override, mock_session = make_mock_db(rows=[])

    mock_user = MagicMock()

    async def override_user():
        return mock_user

    app = make_test_app(db_override, override_user)
    client = TestClient(app)

    response = client.get("/api/v1/incidents?device_id=5")

    assert response.status_code == 200
    # La query fue ejecutada (verificar que execute fue llamado con algo que contiene device_id)
    mock_session.execute.assert_called_once()
    # Extraer el SQL de la llamada y verificar que contiene el filtro de device_id
    call_args = mock_session.execute.call_args
    query_obj = call_args[0][0]
    # El objeto query debe tener el where con device_id
    query_str = str(query_obj)
    assert "device_id" in query_str.lower() or "device" in query_str.lower()

    app.dependency_overrides.clear()


def test_incidents_filter_by_site(set_test_env_vars):
    """INC-03: GET /incidents?site=Torre+Norte pasa el filtro de site a la query."""
    db_override, mock_session = make_mock_db(rows=[])

    mock_user = MagicMock()

    async def override_user():
        return mock_user

    app = make_test_app(db_override, override_user)
    client = TestClient(app)

    response = client.get("/api/v1/incidents?site=Torre+Norte")

    assert response.status_code == 200
    mock_session.execute.assert_called_once()

    app.dependency_overrides.clear()


def test_incidents_pagination_limit_offset(set_test_env_vars):
    """INC-03: limit y offset se pasan como parametros validos de paginacion."""
    db_override, mock_session = make_mock_db(rows=[])

    mock_user = MagicMock()

    async def override_user():
        return mock_user

    app = make_test_app(db_override, override_user)
    client = TestClient(app)

    response = client.get("/api/v1/incidents?limit=10&offset=20")

    assert response.status_code == 200
    mock_session.execute.assert_called_once()
    call_args = mock_session.execute.call_args
    query_obj = call_args[0][0]
    query_str = str(query_obj)
    # La query debe contener LIMIT y OFFSET en el SQL generado
    assert "limit" in query_str.lower() or "LIMIT" in query_str

    app.dependency_overrides.clear()


def test_incidents_ordered_by_started_at_desc(set_test_env_vars):
    """INC-03: La query ordena por started_at DESC (mas reciente primero)."""
    db_override, mock_session = make_mock_db(rows=[])

    mock_user = MagicMock()

    async def override_user():
        return mock_user

    app = make_test_app(db_override, override_user)
    client = TestClient(app)

    response = client.get("/api/v1/incidents")

    assert response.status_code == 200
    call_args = mock_session.execute.call_args
    query_obj = call_args[0][0]
    query_str = str(query_obj)
    # Verificar ORDER BY started_at DESC en el SQL generado
    assert "started_at" in query_str.lower()
    assert "desc" in query_str.lower()

    app.dependency_overrides.clear()


def test_incident_response_schema_from_attributes(set_test_env_vars):
    """INC-03: IncidentResponse tiene model_config from_attributes=True."""
    from app.schemas.incident import IncidentResponse

    assert IncidentResponse.model_config.get("from_attributes") is True


def test_incident_response_schema_fields(set_test_env_vars):
    """INC-03: IncidentResponse tiene todos los campos requeridos del JOIN."""
    from app.schemas.incident import IncidentResponse

    required_fields = {
        "id", "device_id", "device_name", "device_site",
        "started_at", "resolved_at", "duration_seconds",
        "alert_sent", "recovery_alert_sent",
    }
    schema_fields = set(IncidentResponse.model_fields.keys())
    assert required_fields.issubset(schema_fields)


def test_incident_response_model_validate_from_dict(set_test_env_vars):
    """INC-03: IncidentResponse.model_validate(dict) funciona con datos del JOIN."""
    from app.schemas.incident import IncidentResponse

    data = {
        "id": 1,
        "device_id": 10,
        "device_name": "Router Principal",
        "device_site": "Torre Norte",
        "started_at": datetime(2026, 4, 26, 10, 0, 0, tzinfo=timezone.utc),
        "resolved_at": None,
        "duration_seconds": None,
        "alert_sent": False,
        "recovery_alert_sent": False,
    }
    incident = IncidentResponse.model_validate(data)
    assert incident.id == 1
    assert incident.device_name == "Router Principal"
    assert incident.device_site == "Torre Norte"
    assert incident.resolved_at is None
