"""
Tests del servicio Telegram para BEEPYRED NOC.

ALERT-02: format_down_message() produce HTML con nombre, IP en code, sitio, timestamp UTC.
ALERT-03: format_up_message() formatea duracion correctamente.
send_telegram_alert() guard si token/chat_id vacios; usa async with Bot + parse_mode HTML.

CRITICO: No realiza llamadas reales a la API de Telegram.
Usa unittest.mock para aislar telegram.Bot como context manager async.
"""
import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Tests de format_down_message (ALERT-02)
# ---------------------------------------------------------------------------

def test_format_down_message_includes_device_name(set_test_env_vars):
    """ALERT-02: format_down_message() incluye el nombre del equipo."""
    from app.services.telegram import format_down_message

    result = format_down_message(
        device_name="Router Principal",
        ip="192.168.1.1",
        site="Torre Norte",
        timestamp=datetime(2026, 4, 26, 10, 30, 0, tzinfo=timezone.utc),
    )
    assert "Router Principal" in result


def test_format_down_message_includes_ip_in_code_tag(set_test_env_vars):
    """ALERT-02: format_down_message() incluye la IP dentro de etiqueta HTML <code>."""
    from app.services.telegram import format_down_message

    result = format_down_message(
        device_name="Router Principal",
        ip="10.0.0.5",
        site="Torre Norte",
        timestamp=datetime(2026, 4, 26, 10, 30, 0, tzinfo=timezone.utc),
    )
    assert "<code>10.0.0.5</code>" in result


def test_format_down_message_includes_site(set_test_env_vars):
    """ALERT-02: format_down_message() incluye el nombre del sitio."""
    from app.services.telegram import format_down_message

    result = format_down_message(
        device_name="OLT Centro",
        ip="172.16.1.10",
        site="Nodo Centro",
        timestamp=datetime(2026, 4, 26, 15, 0, 0, tzinfo=timezone.utc),
    )
    assert "Nodo Centro" in result


def test_format_down_message_uses_sin_sitio_when_site_is_none(set_test_env_vars):
    """ALERT-02: format_down_message() usa 'Sin sitio' cuando site es None."""
    from app.services.telegram import format_down_message

    result = format_down_message(
        device_name="ONU 001",
        ip="10.1.1.50",
        site=None,
        timestamp=datetime(2026, 4, 26, 8, 0, 0, tzinfo=timezone.utc),
    )
    assert "Sin sitio" in result


def test_format_down_message_includes_timestamp_utc(set_test_env_vars):
    """ALERT-02: format_down_message() incluye timestamp formateado como dd/mm/yyyy HH:MM:SS UTC."""
    from app.services.telegram import format_down_message

    ts = datetime(2026, 4, 26, 14, 55, 30, tzinfo=timezone.utc)
    result = format_down_message(
        device_name="Router",
        ip="192.168.1.1",
        site="Torre",
        timestamp=ts,
    )
    assert "26/04/2026 14:55:30" in result
    assert "UTC" in result


# ---------------------------------------------------------------------------
# Tests de format_up_message (ALERT-03)
# ---------------------------------------------------------------------------

def test_format_up_message_includes_equipo_recuperado(set_test_env_vars):
    """ALERT-03: format_up_message() incluye 'EQUIPO RECUPERADO' en el resultado."""
    from app.services.telegram import format_up_message

    result = format_up_message(
        device_name="Router Principal",
        ip="192.168.1.1",
        site="Torre Norte",
        duration_seconds=300,
    )
    assert "EQUIPO RECUPERADO" in result


def test_format_up_message_formats_duration_with_hours(set_test_env_vars):
    """ALERT-03: format_up_message() formatea 3661 segundos como '1h 1m 1s'."""
    from app.services.telegram import format_up_message

    result = format_up_message(
        device_name="Router",
        ip="192.168.1.1",
        site=None,
        duration_seconds=3661,
    )
    assert "1h 1m 1s" in result


def test_format_up_message_formats_duration_without_hours(set_test_env_vars):
    """ALERT-03: format_up_message() formatea 90 segundos como '1m 30s' (sin horas)."""
    from app.services.telegram import format_up_message

    result = format_up_message(
        device_name="Router",
        ip="192.168.1.1",
        site=None,
        duration_seconds=90,
    )
    assert "1m 30s" in result
    # No debe incluir "0h"
    assert "0h" not in result


# ---------------------------------------------------------------------------
# Tests de send_telegram_alert
# ---------------------------------------------------------------------------

def test_send_telegram_alert_does_nothing_when_token_empty(set_test_env_vars, monkeypatch):
    """send_telegram_alert() retorna sin llamar Bot si TELEGRAM_BOT_TOKEN esta vacio."""
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "")

    import importlib
    import app.core.config as config_module
    importlib.reload(config_module)

    import app.services.telegram as tg_module
    importlib.reload(tg_module)

    # Verificar que _get_bot_class (y por ende Bot) no se llama cuando token esta vacio
    mock_get_bot_class = MagicMock()
    with patch.object(tg_module, "_get_bot_class", mock_get_bot_class):
        asyncio.run(tg_module.send_telegram_alert("test"))

    mock_get_bot_class.assert_not_called()


def test_send_telegram_alert_calls_send_message_with_html(set_test_env_vars, monkeypatch):
    """send_telegram_alert() llama bot.send_message() con parse_mode='HTML'."""
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake_token_123")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "987654321")

    import importlib
    import app.core.config as config_module
    importlib.reload(config_module)

    # Crear mock del Bot como context manager async
    mock_bot_instance = AsyncMock()
    mock_bot_instance.send_message = AsyncMock()

    mock_bot_cm = MagicMock()
    mock_bot_cm.__aenter__ = AsyncMock(return_value=mock_bot_instance)
    mock_bot_cm.__aexit__ = AsyncMock(return_value=False)

    mock_bot_class = MagicMock(return_value=mock_bot_cm)

    import app.services.telegram as tg_module
    importlib.reload(tg_module)

    with patch.object(tg_module, "_get_bot_class", return_value=mock_bot_class):
        asyncio.run(tg_module.send_telegram_alert("mensaje de prueba"))

    mock_bot_instance.send_message.assert_called_once()
    call_kwargs = mock_bot_instance.send_message.call_args[1]
    assert call_kwargs.get("parse_mode") == "HTML"


def test_send_telegram_alert_uses_async_context_manager(set_test_env_vars, monkeypatch):
    """send_telegram_alert() usa async with Bot(...) — inicializa la sesion HTTP."""
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake_token_456")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "111222333")

    import importlib
    import app.core.config as config_module
    importlib.reload(config_module)

    mock_bot_instance = AsyncMock()
    mock_bot_instance.send_message = AsyncMock()

    mock_bot_cm = MagicMock()
    mock_bot_cm.__aenter__ = AsyncMock(return_value=mock_bot_instance)
    mock_bot_cm.__aexit__ = AsyncMock(return_value=False)

    mock_bot_class = MagicMock(return_value=mock_bot_cm)

    import app.services.telegram as tg_module
    importlib.reload(tg_module)

    with patch.object(tg_module, "_get_bot_class", return_value=mock_bot_class):
        asyncio.run(tg_module.send_telegram_alert("test msg"))

    # __aenter__ debio ser llamado (uso de async with)
    mock_bot_cm.__aenter__.assert_called_once()
    mock_bot_cm.__aexit__.assert_called_once()
