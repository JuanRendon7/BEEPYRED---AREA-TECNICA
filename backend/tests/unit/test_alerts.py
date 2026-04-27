"""
Tests del pipeline de alertas y ciclo de vida de incidentes — BEEPYRED NOC.

ALERT-01: handle_device_down encola con countdown (debounce anti-flapping)
ALERT-04: al ejecutarse, verifica si el incidente sigue abierto
ALERT-05: alert_sent / recovery_alert_sent marcados en DB tras enviar alerta
INC-01:   open_incident_if_not_exists — INSERT con SELECT FOR UPDATE
INC-02:   close_incident — UPDATE resolved_at + duration_seconds

CRITICO: No conecta a PostgreSQL ni Telegram reales.
Usa AsyncMock para simular AsyncSessionLocal y send_telegram_alert.
"""
import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest


# ---------------------------------------------------------------------------
# Helpers para construir objetos mock de Device e Incident
# ---------------------------------------------------------------------------

def make_device(id=1, name="Router Principal", ip="192.168.1.1", site="Torre Norte"):
    """Crea un objeto Device-like para tests."""
    d = MagicMock()
    d.id = id
    d.name = name
    d.ip_address = ip
    d.site = site
    return d


def make_incident(
    id=10,
    device_id=1,
    started_at=None,
    resolved_at=None,
    duration_seconds=None,
    alert_sent=False,
    recovery_alert_sent=False,
):
    """Crea un objeto Incident-like para tests."""
    inc = MagicMock()
    inc.id = id
    inc.device_id = device_id
    inc.started_at = started_at or datetime(2026, 4, 26, 10, 0, 0, tzinfo=timezone.utc)
    inc.resolved_at = resolved_at
    inc.duration_seconds = duration_seconds
    inc.alert_sent = alert_sent
    inc.recovery_alert_sent = recovery_alert_sent
    return inc


def make_db_session(device=None, incident=None):
    """
    Construye un mock de AsyncSession que retorna device e incident
    en llamadas consecutivas a execute().
    """
    mock_device_result = MagicMock()
    mock_device_result.scalar_one_or_none.return_value = device

    mock_incident_result = MagicMock()
    mock_incident_result.scalar_one_or_none.return_value = incident

    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    # Primera execute -> device, segunda execute -> incident
    mock_session.execute = AsyncMock(
        side_effect=[mock_device_result, mock_incident_result]
    )
    mock_session.commit = AsyncMock()
    mock_session.flush = AsyncMock()
    mock_session.add = MagicMock()

    mock_factory = MagicMock(return_value=mock_session)
    return mock_factory, mock_session


# ---------------------------------------------------------------------------
# Tests de handle_device_down
# ---------------------------------------------------------------------------

def test_handle_device_down_skips_if_incident_already_closed(set_test_env_vars):
    """
    ALERT-04: si el incidente ya esta cerrado (resolved_at != None) cuando se
    ejecuta handle_device_down, retorna sin enviar Telegram.
    """
    from app.tasks.alerts import _handle_device_down_async

    device = make_device()
    # Incidente ya cerrado — el equipo se recupero antes del countdown
    closed_incident = make_incident(resolved_at=datetime(2026, 4, 26, 10, 5, 0, tzinfo=timezone.utc))

    mock_factory, mock_session = make_db_session(device=device, incident=closed_incident)

    with patch("app.tasks.alerts.AsyncSessionLocal", mock_factory), \
         patch("app.tasks.alerts.send_telegram_alert", new_callable=AsyncMock) as mock_tg:
        result = asyncio.run(_handle_device_down_async(1))

    mock_tg.assert_not_called()
    assert result["skipped"] is True
    assert result["reason"] == "recovered_before_debounce"


def test_handle_device_down_creates_incident_if_none_exists(set_test_env_vars):
    """
    INC-01: si no hay incidente abierto, open_incident_if_not_exists crea uno nuevo.
    """
    from app.tasks.alerts import _handle_device_down_async

    device = make_device()

    # Simular que no existe incidente previo — open_incident_if_not_exists crea uno
    # Para este test, hacemos que execute devuelva None para el incidente (no existe)
    # y que db.add + db.flush simulen la insercion
    mock_device_result = MagicMock()
    mock_device_result.scalar_one_or_none.return_value = device

    mock_incident_result = MagicMock()
    mock_incident_result.scalar_one_or_none.return_value = None  # no existe incidente

    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    mock_session.execute = AsyncMock(
        side_effect=[mock_device_result, mock_incident_result]
    )
    mock_session.commit = AsyncMock()
    mock_session.flush = AsyncMock()
    mock_session.add = MagicMock()

    mock_factory = MagicMock(return_value=mock_session)

    with patch("app.tasks.alerts.AsyncSessionLocal", mock_factory), \
         patch("app.tasks.alerts.send_telegram_alert", new_callable=AsyncMock):
        asyncio.run(_handle_device_down_async(1))

    # db.add debe haber sido llamado con un nuevo Incident
    mock_session.add.assert_called_once()
    # db.flush debe haberse llamado para obtener el ID asignado
    mock_session.flush.assert_called_once()


def test_handle_device_down_reuses_existing_open_incident(set_test_env_vars):
    """
    INC-01: si ya hay un incidente abierto, open_incident_if_not_exists lo reutiliza
    — no crea un duplicado.
    """
    from app.tasks.alerts import _handle_device_down_async

    device = make_device()
    existing_incident = make_incident(alert_sent=False)  # incidente abierto, alerta no enviada

    mock_factory, mock_session = make_db_session(device=device, incident=existing_incident)

    with patch("app.tasks.alerts.AsyncSessionLocal", mock_factory), \
         patch("app.tasks.alerts.send_telegram_alert", new_callable=AsyncMock):
        asyncio.run(_handle_device_down_async(1))

    # db.add NO debe ser llamado — reutiliza el existente
    mock_session.add.assert_not_called()


def test_handle_device_down_marks_alert_sent_true(set_test_env_vars):
    """
    ALERT-05: alert_sent=True se marca en el incidente despues de enviar Telegram DOWN.
    """
    from app.tasks.alerts import _handle_device_down_async

    device = make_device()
    open_incident = make_incident(alert_sent=False)

    mock_factory, mock_session = make_db_session(device=device, incident=open_incident)

    with patch("app.tasks.alerts.AsyncSessionLocal", mock_factory), \
         patch("app.tasks.alerts.send_telegram_alert", new_callable=AsyncMock):
        asyncio.run(_handle_device_down_async(1))

    assert open_incident.alert_sent is True
    mock_session.commit.assert_called_once()


def test_handle_device_down_sends_telegram_with_device_name(set_test_env_vars):
    """
    ALERT-02: handle_device_down llama send_telegram_alert con mensaje que contiene
    el nombre del equipo.
    """
    from app.tasks.alerts import _handle_device_down_async

    device = make_device(name="MikroTik Core")
    open_incident = make_incident(alert_sent=False)

    mock_factory, mock_session = make_db_session(device=device, incident=open_incident)

    with patch("app.tasks.alerts.AsyncSessionLocal", mock_factory), \
         patch("app.tasks.alerts.send_telegram_alert", new_callable=AsyncMock) as mock_tg:
        asyncio.run(_handle_device_down_async(1))

    mock_tg.assert_called_once()
    sent_text = mock_tg.call_args[0][0]
    assert "MikroTik Core" in sent_text


def test_handle_device_down_skips_if_device_not_found(set_test_env_vars):
    """
    T-3-11: si device_id no existe en DB, retorna skipped sin ejecutar logica de alertas.
    """
    from app.tasks.alerts import _handle_device_down_async

    mock_device_result = MagicMock()
    mock_device_result.scalar_one_or_none.return_value = None  # device no existe

    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    mock_session.execute = AsyncMock(return_value=mock_device_result)
    mock_factory = MagicMock(return_value=mock_session)

    with patch("app.tasks.alerts.AsyncSessionLocal", mock_factory), \
         patch("app.tasks.alerts.send_telegram_alert", new_callable=AsyncMock) as mock_tg:
        result = asyncio.run(_handle_device_down_async(999))

    mock_tg.assert_not_called()
    assert result["skipped"] is True
    assert result["reason"] == "device_not_found"


# ---------------------------------------------------------------------------
# Tests de handle_device_recovery
# ---------------------------------------------------------------------------

def test_handle_device_recovery_skips_if_no_open_incident(set_test_env_vars):
    """
    Edge case: recovery sin DOWN registrado — retorna sin error.
    """
    from app.tasks.alerts import _handle_device_recovery_async

    device = make_device()

    mock_device_result = MagicMock()
    mock_device_result.scalar_one_or_none.return_value = device

    mock_incident_result = MagicMock()
    mock_incident_result.scalar_one_or_none.return_value = None  # no hay incidente abierto

    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    mock_session.execute = AsyncMock(
        side_effect=[mock_device_result, mock_incident_result]
    )
    mock_factory = MagicMock(return_value=mock_session)

    with patch("app.tasks.alerts.AsyncSessionLocal", mock_factory), \
         patch("app.tasks.alerts.send_telegram_alert", new_callable=AsyncMock) as mock_tg:
        result = asyncio.run(_handle_device_recovery_async(1))

    mock_tg.assert_not_called()
    assert result["skipped"] is True
    assert result["reason"] == "no_open_incident"


def test_handle_device_recovery_closes_incident_with_duration(set_test_env_vars):
    """
    INC-02: close_incident establece resolved_at y calcula duration_seconds.
    """
    from app.tasks.alerts import _handle_device_recovery_async

    device = make_device()
    started = datetime(2026, 4, 26, 10, 0, 0, tzinfo=timezone.utc)
    open_incident = make_incident(started_at=started, resolved_at=None)
    # Simular que close_incident modifica resolved_at y duration_seconds
    # (lo hace directamente sobre el objeto, como el codigo real)

    mock_device_result = MagicMock()
    mock_device_result.scalar_one_or_none.return_value = device

    mock_incident_result = MagicMock()
    mock_incident_result.scalar_one_or_none.return_value = open_incident

    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    mock_session.execute = AsyncMock(
        side_effect=[mock_device_result, mock_incident_result]
    )
    mock_session.commit = AsyncMock()
    mock_factory = MagicMock(return_value=mock_session)

    with patch("app.tasks.alerts.AsyncSessionLocal", mock_factory), \
         patch("app.tasks.alerts.send_telegram_alert", new_callable=AsyncMock):
        asyncio.run(_handle_device_recovery_async(1))

    # resolved_at debe haber sido asignado
    assert open_incident.resolved_at is not None
    # duration_seconds debe ser un entero positivo
    assert isinstance(open_incident.duration_seconds, int)
    assert open_incident.duration_seconds >= 0


def test_handle_device_recovery_marks_recovery_alert_sent(set_test_env_vars):
    """
    ALERT-05: recovery_alert_sent=True se marca despues de enviar Telegram UP.
    """
    from app.tasks.alerts import _handle_device_recovery_async

    device = make_device()
    open_incident = make_incident(recovery_alert_sent=False)

    mock_device_result = MagicMock()
    mock_device_result.scalar_one_or_none.return_value = device

    mock_incident_result = MagicMock()
    mock_incident_result.scalar_one_or_none.return_value = open_incident

    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    mock_session.execute = AsyncMock(
        side_effect=[mock_device_result, mock_incident_result]
    )
    mock_session.commit = AsyncMock()
    mock_factory = MagicMock(return_value=mock_session)

    with patch("app.tasks.alerts.AsyncSessionLocal", mock_factory), \
         patch("app.tasks.alerts.send_telegram_alert", new_callable=AsyncMock):
        asyncio.run(_handle_device_recovery_async(1))

    assert open_incident.recovery_alert_sent is True
    mock_session.commit.assert_called_once()


def test_handle_device_recovery_sends_telegram_with_duration(set_test_env_vars):
    """
    ALERT-03: handle_device_recovery llama send_telegram_alert con mensaje que
    incluye la duracion de la caida.
    """
    from app.tasks.alerts import _handle_device_recovery_async

    device = make_device(name="OLT Norte")
    started = datetime(2026, 4, 26, 10, 0, 0, tzinfo=timezone.utc)
    # Incidente con duracion preexistente (sera recalculada por close_incident)
    open_incident = make_incident(started_at=started)

    mock_device_result = MagicMock()
    mock_device_result.scalar_one_or_none.return_value = device

    mock_incident_result = MagicMock()
    mock_incident_result.scalar_one_or_none.return_value = open_incident

    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    mock_session.execute = AsyncMock(
        side_effect=[mock_device_result, mock_incident_result]
    )
    mock_session.commit = AsyncMock()
    mock_factory = MagicMock(return_value=mock_session)

    with patch("app.tasks.alerts.AsyncSessionLocal", mock_factory), \
         patch("app.tasks.alerts.send_telegram_alert", new_callable=AsyncMock) as mock_tg:
        asyncio.run(_handle_device_recovery_async(1))

    mock_tg.assert_called_once()
    sent_text = mock_tg.call_args[0][0]
    # El mensaje UP debe contener el nombre del equipo y el indicador de recuperacion
    assert "OLT Norte" in sent_text
    assert "RECUPERADO" in sent_text


# ---------------------------------------------------------------------------
# Tests de open_incident_if_not_exists (INC-01)
# ---------------------------------------------------------------------------

def test_open_incident_uses_with_for_update(set_test_env_vars):
    """
    INC-01: open_incident_if_not_exists usa .with_for_update() para prevenir
    race conditions entre workers Celery paralelos.
    """
    # Este test verifica que la query SQL incluye FOR UPDATE
    # Inspeccionamos el codigo fuente para confirmar el patron
    import inspect
    from app.tasks.alerts import open_incident_if_not_exists

    source = inspect.getsource(open_incident_if_not_exists)
    assert "with_for_update" in source


def test_open_incident_returns_existing_if_already_open(set_test_env_vars):
    """
    INC-01: si ya existe un incidente abierto, open_incident_if_not_exists
    lo retorna sin insertar un duplicado.
    """
    from app.tasks.alerts import open_incident_if_not_exists

    existing_incident = make_incident()

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = existing_incident

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=mock_result)
    mock_session.add = MagicMock()
    mock_session.flush = AsyncMock()

    result = asyncio.run(open_incident_if_not_exists(mock_session, device_id=1))

    assert result is existing_incident
    mock_session.add.assert_not_called()


# ---------------------------------------------------------------------------
# Tests de close_incident (INC-02)
# ---------------------------------------------------------------------------

def test_close_incident_calculates_duration_seconds(set_test_env_vars):
    """
    INC-02: close_incident calcula duration_seconds = (resolved_at - started_at).total_seconds()
    """
    from app.tasks.alerts import close_incident

    started = datetime(2026, 4, 26, 10, 0, 0, tzinfo=timezone.utc)
    open_incident = make_incident(started_at=started)

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = open_incident

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=mock_result)

    result = asyncio.run(close_incident(mock_session, device_id=1))

    assert result is open_incident
    assert result.resolved_at is not None
    assert isinstance(result.duration_seconds, int)
    assert result.duration_seconds >= 0


def test_close_incident_returns_none_if_no_open_incident(set_test_env_vars):
    """
    INC-02: close_incident retorna None si no hay incidente abierto.
    """
    from app.tasks.alerts import close_incident

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=mock_result)

    result = asyncio.run(close_incident(mock_session, device_id=1))

    assert result is None
