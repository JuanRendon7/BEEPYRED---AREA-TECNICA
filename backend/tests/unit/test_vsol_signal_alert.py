"""
Tests de alerta Telegram por señal optica baja — VSOL-03/ALERT-02.

Cubre:
- No alerta si señal >= umbral
- No alerta si ya se alertó en la última hora (debounce via Redis TTL)
- Alerta enviada si señal < umbral y sin alerta previa
- Clave Redis usa prefijo 'vsol:signal_alert:' (no 'cb:')
- TTL correcto al setear la clave de debounce
"""
import asyncio
from unittest.mock import AsyncMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_redis_mock(key_exists: bool = False):
    mock = AsyncMock()
    mock.exists = AsyncMock(return_value=1 if key_exists else 0)
    mock.setex = AsyncMock(return_value=True)
    return mock


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_no_alert_when_signal_above_threshold(set_test_env_vars):
    """Sin alerta si Rx >= ONU_SIGNAL_MIN_DBM (-28.0 dBm por defecto)."""
    from app.tasks.vsol import _check_signal_alert

    redis_mock = _make_redis_mock(key_exists=False)

    with patch("app.tasks.vsol.send_telegram_alert") as mock_send:
        asyncio.run(_check_signal_alert(
            redis_mock,
            onu_id=1,
            serial_number="4857454c12345601",
            signal_rx_dbm=-20.0,  # bien por encima del umbral
            olt_name="OLT-San-Luis",
        ))

    mock_send.assert_not_called()
    redis_mock.setex.assert_not_called()


def test_no_alert_when_already_alerted(set_test_env_vars):
    """Sin alerta si la clave debounce ya existe en Redis."""
    from app.tasks.vsol import _check_signal_alert

    redis_mock = _make_redis_mock(key_exists=True)  # ya alertado

    with patch("app.tasks.vsol.send_telegram_alert") as mock_send:
        asyncio.run(_check_signal_alert(
            redis_mock,
            onu_id=5,
            serial_number="ABCDEF1234567890",
            signal_rx_dbm=-30.0,  # por debajo del umbral
            olt_name="OLT-San-Luis",
        ))

    mock_send.assert_not_called()


def test_alert_sent_when_signal_below_threshold(set_test_env_vars):
    """Alerta enviada cuando Rx < -28 dBm y no hay debounce activo."""
    from app.tasks.vsol import _check_signal_alert

    redis_mock = _make_redis_mock(key_exists=False)

    with patch("app.tasks.vsol.send_telegram_alert", new_callable=AsyncMock) as mock_send:
        asyncio.run(_check_signal_alert(
            redis_mock,
            onu_id=7,
            serial_number="4857454c12345601",
            signal_rx_dbm=-30.5,
            olt_name="OLT-San-Luis",
        ))

    mock_send.assert_called_once()


def test_alert_message_contains_serial_and_dbm(set_test_env_vars):
    """El mensaje Telegram incluye el serial y el valor de señal."""
    from app.tasks.vsol import _check_signal_alert

    redis_mock = _make_redis_mock(key_exists=False)
    sent_text = []

    async def capture_text(text):
        sent_text.append(text)

    with patch("app.tasks.vsol.send_telegram_alert", side_effect=capture_text):
        asyncio.run(_check_signal_alert(
            redis_mock,
            onu_id=3,
            serial_number="ABCDEF1234567890",
            signal_rx_dbm=-29.50,
            olt_name="OLT-San-Luis",
        ))

    assert len(sent_text) == 1
    assert "ABCDEF1234567890" in sent_text[0]
    assert "-29.50" in sent_text[0]


def test_redis_key_set_after_alert(set_test_env_vars):
    """Tras enviar alerta, se setea clave Redis con TTL para debounce."""
    from app.tasks.vsol import _check_signal_alert, SIGNAL_ALERT_TTL

    redis_mock = _make_redis_mock(key_exists=False)

    with patch("app.tasks.vsol.send_telegram_alert", new_callable=AsyncMock):
        asyncio.run(_check_signal_alert(
            redis_mock,
            onu_id=9,
            serial_number="4857454c12345609",
            signal_rx_dbm=-31.0,
            olt_name="OLT-San-Luis",
        ))

    redis_mock.setex.assert_called_once()
    key, ttl, _ = redis_mock.setex.call_args[0]
    assert "vsol:signal_alert:9" == key
    assert ttl == SIGNAL_ALERT_TTL


def test_redis_key_uses_vsol_prefix_not_cb(set_test_env_vars):
    """La clave debounce usa prefijo 'vsol:signal_alert:' no 'cb:'."""
    from app.tasks.vsol import _check_signal_alert

    redis_mock = _make_redis_mock(key_exists=False)

    with patch("app.tasks.vsol.send_telegram_alert", new_callable=AsyncMock):
        asyncio.run(_check_signal_alert(
            redis_mock,
            onu_id=42,
            serial_number="ABCDEF1234567890",
            signal_rx_dbm=-29.0,
            olt_name="OLT",
        ))

    # Verificar clave Redis usada en exists()
    check_key = redis_mock.exists.call_args[0][0]
    assert check_key.startswith("vsol:signal_alert:"), f"Clave invalida: {check_key}"
    assert not check_key.startswith("cb:")


def test_no_alert_at_exact_threshold(set_test_env_vars):
    """Señal exactamente en el umbral (-28.0) NO genera alerta."""
    from app.tasks.vsol import _check_signal_alert
    from app.core.config import settings

    redis_mock = _make_redis_mock(key_exists=False)

    with patch("app.tasks.vsol.send_telegram_alert") as mock_send:
        asyncio.run(_check_signal_alert(
            redis_mock,
            onu_id=1,
            serial_number="ABCDEF1234567890",
            signal_rx_dbm=settings.ONU_SIGNAL_MIN_DBM,  # exactamente en el umbral
            olt_name="OLT",
        ))

    mock_send.assert_not_called()
