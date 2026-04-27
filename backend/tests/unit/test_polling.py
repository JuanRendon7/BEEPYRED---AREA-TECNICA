"""
Tests del worker de polling ICMP — POLL-01 a POLL-05.

CRITICO: estos tests NO ejecutan ping real ni conectan a Redis/DB.
Usan unittest.mock para aislar las dependencias externas.
- ping_host: mock de asyncio.create_subprocess_exec
- Redis: mock de aioredis.from_url
- DB: mock de AsyncSessionLocal
"""
import asyncio
import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.device import Device, DeviceStatus


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def device_up():
    """Device fixture con estado inicial UP."""
    d = Device()
    d.id = 1
    d.ip_address = "192.168.1.1"
    d.status = DeviceStatus.UP
    d.consecutive_failures = 0
    d.is_active = True
    d.last_seen_at = None
    return d


@pytest.fixture
def device_unknown():
    """Device fixture con estado inicial UNKNOWN."""
    d = Device()
    d.id = 2
    d.ip_address = "10.0.0.1"
    d.status = DeviceStatus.UNKNOWN
    d.consecutive_failures = 0
    d.is_active = True
    d.last_seen_at = None
    return d


# ---------------------------------------------------------------------------
# Tests de ping_host
# ---------------------------------------------------------------------------

def test_ping_host_returns_true_on_returncode_0(set_test_env_vars):
    """POLL-05: ping_host retorna True cuando returncode == 0."""
    from app.tasks.polling import ping_host

    mock_proc = AsyncMock()
    mock_proc.returncode = 0
    mock_proc.wait = AsyncMock()

    with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
        result = asyncio.run(ping_host("192.168.1.1", timeout=5))

    assert result is True


def test_ping_host_returns_false_on_returncode_1(set_test_env_vars):
    """POLL-05: ping_host retorna False cuando returncode != 0."""
    from app.tasks.polling import ping_host

    mock_proc = AsyncMock()
    mock_proc.returncode = 1
    mock_proc.wait = AsyncMock()

    with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
        result = asyncio.run(ping_host("192.168.1.1", timeout=5))

    assert result is False


def test_ping_host_returns_false_on_timeout(set_test_env_vars):
    """POLL-05: ping_host retorna False si asyncio.wait_for lanza TimeoutError."""
    from app.tasks.polling import ping_host

    mock_proc = AsyncMock()
    mock_proc.returncode = None  # nunca termino
    mock_proc.wait = AsyncMock(side_effect=asyncio.TimeoutError())
    mock_proc.kill = MagicMock()

    with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
        result = asyncio.run(ping_host("192.168.1.1", timeout=1))

    assert result is False


def test_ping_host_kills_process_on_timeout(set_test_env_vars):
    """POLL-05: ping_host llama proc.kill() cuando hay TimeoutError."""
    from app.tasks.polling import ping_host

    mock_proc = AsyncMock()
    mock_proc.returncode = None
    mock_proc.wait = AsyncMock(side_effect=asyncio.TimeoutError())
    mock_proc.kill = MagicMock()

    with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
        asyncio.run(ping_host("192.168.1.1", timeout=1))

    mock_proc.kill.assert_called_once()


def test_semaphore_max_concurrent_connections(set_test_env_vars):
    """POLL-02: _semaphore es asyncio.Semaphore con valor de MAX_CONCURRENT_CONNECTIONS."""
    from app.tasks.polling import _semaphore
    # Verificar que el semaforo tiene la capacidad correcta
    # asyncio.Semaphore almacena el valor inicial en _value
    assert isinstance(_semaphore, asyncio.Semaphore)
    # El valor del semaforo debe ser MAX_CONCURRENT_CONNECTIONS (50 por defecto)
    from app.core.config import settings
    assert _semaphore._value == settings.MAX_CONCURRENT_CONNECTIONS


# ---------------------------------------------------------------------------
# Tests de logica consecutive_failures (POLL-03)
# ---------------------------------------------------------------------------

def test_consecutive_failures_increments_on_failure(set_test_env_vars):
    """POLL-03: consecutive_failures se incrementa en cada fallo (< threshold no es DOWN)."""
    from app.tasks.polling import _ping_and_update

    # Crear device con 1 fallo previo
    device = Device()
    device.id = 1
    device.ip_address = "192.168.1.1"
    device.status = DeviceStatus.UP
    device.consecutive_failures = 1
    device.is_active = True
    device.last_seen_at = None

    # Mock: ping falla; DB retorna el mismo device
    mock_db_device = Device()
    mock_db_device.id = 1
    mock_db_device.ip_address = "192.168.1.1"
    mock_db_device.status = DeviceStatus.UP
    mock_db_device.consecutive_failures = 1
    mock_db_device.is_active = True
    mock_db_device.last_seen_at = None

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_db_device

    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    mock_session.execute = AsyncMock(return_value=mock_result)
    mock_session.commit = AsyncMock()

    mock_session_factory = MagicMock()
    mock_session_factory.return_value = mock_session

    with patch("app.tasks.polling.ping_host", return_value=False), \
         patch("app.tasks.polling.AsyncSessionLocal", mock_session_factory), \
         patch("app.tasks.polling.publish_status_update", new_callable=AsyncMock):
        asyncio.run(_ping_and_update(device))

    # consecutive_failures debe ser 2 (1 previo + 1 nuevo fallo)
    assert mock_db_device.consecutive_failures == 2
    # Con THRESHOLD=3, todavia no es DOWN
    assert mock_db_device.status == DeviceStatus.UP


def test_consecutive_failures_down_at_threshold(set_test_env_vars):
    """POLL-03: status pasa a DOWN cuando consecutive_failures >= CONSECUTIVE_FAILURES_THRESHOLD (3)."""
    from app.tasks.polling import _ping_and_update
    from app.core.config import settings

    device = Device()
    device.id = 1
    device.ip_address = "192.168.1.1"
    device.status = DeviceStatus.UP
    device.consecutive_failures = settings.CONSECUTIVE_FAILURES_THRESHOLD - 1  # 2
    device.is_active = True
    device.last_seen_at = None

    mock_db_device = Device()
    mock_db_device.id = 1
    mock_db_device.ip_address = "192.168.1.1"
    mock_db_device.status = DeviceStatus.UP
    mock_db_device.consecutive_failures = settings.CONSECUTIVE_FAILURES_THRESHOLD - 1
    mock_db_device.is_active = True
    mock_db_device.last_seen_at = None

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_db_device
    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    mock_session.execute = AsyncMock(return_value=mock_result)
    mock_session.commit = AsyncMock()
    mock_session_factory = MagicMock()
    mock_session_factory.return_value = mock_session

    with patch("app.tasks.polling.ping_host", return_value=False), \
         patch("app.tasks.polling.AsyncSessionLocal", mock_session_factory), \
         patch("app.tasks.polling.publish_status_update", new_callable=AsyncMock):
        asyncio.run(_ping_and_update(device))

    assert mock_db_device.consecutive_failures == settings.CONSECUTIVE_FAILURES_THRESHOLD
    assert mock_db_device.status == DeviceStatus.DOWN


def test_consecutive_failures_reset_on_success(set_test_env_vars):
    """POLL-03: consecutive_failures se resetea a 0 cuando el equipo vuelve a responder."""
    from app.tasks.polling import _ping_and_update

    device = Device()
    device.id = 1
    device.ip_address = "192.168.1.1"
    device.status = DeviceStatus.DOWN
    device.consecutive_failures = 3
    device.is_active = True
    device.last_seen_at = None

    mock_db_device = Device()
    mock_db_device.id = 1
    mock_db_device.ip_address = "192.168.1.1"
    mock_db_device.status = DeviceStatus.DOWN
    mock_db_device.consecutive_failures = 3
    mock_db_device.is_active = True
    mock_db_device.last_seen_at = None

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_db_device
    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    mock_session.execute = AsyncMock(return_value=mock_result)
    mock_session.commit = AsyncMock()
    mock_session_factory = MagicMock()
    mock_session_factory.return_value = mock_session

    with patch("app.tasks.polling.ping_host", return_value=True), \
         patch("app.tasks.polling.AsyncSessionLocal", mock_session_factory), \
         patch("app.tasks.polling.publish_status_update", new_callable=AsyncMock):
        asyncio.run(_ping_and_update(device))

    assert mock_db_device.consecutive_failures == 0
    assert mock_db_device.status == DeviceStatus.UP
    assert mock_db_device.last_seen_at is not None


# ---------------------------------------------------------------------------
# Tests de Redis pub/sub (POLL-04)
# ---------------------------------------------------------------------------

def test_publish_status_update_publishes_correct_payload(set_test_env_vars):
    """POLL-04: publish_status_update publica JSON con id y status al canal 'device_status'."""
    from app.tasks.polling import publish_status_update

    mock_redis = AsyncMock()
    mock_redis.publish = AsyncMock()
    mock_redis.aclose = AsyncMock()

    with patch("app.tasks.polling.aioredis.from_url", return_value=mock_redis):
        asyncio.run(publish_status_update(42, "down"))

    mock_redis.publish.assert_called_once()
    call_args = mock_redis.publish.call_args
    channel = call_args[0][0]
    payload_str = call_args[0][1]
    payload = json.loads(payload_str)

    assert channel == "device_status"
    assert payload["id"] == 42
    assert payload["status"] == "down"


def test_publish_status_update_closes_redis_connection(set_test_env_vars):
    """POLL-04: publish_status_update cierra la conexion Redis con aclose()."""
    from app.tasks.polling import publish_status_update

    mock_redis = AsyncMock()
    mock_redis.publish = AsyncMock()
    mock_redis.aclose = AsyncMock()

    with patch("app.tasks.polling.aioredis.from_url", return_value=mock_redis):
        asyncio.run(publish_status_update(1, "up"))

    mock_redis.aclose.assert_called_once()


# ---------------------------------------------------------------------------
# Test de beat schedule (POLL-01)
# ---------------------------------------------------------------------------

def test_beat_schedule_has_poll_all_devices(set_test_env_vars):
    """POLL-01: celery_app.beat_schedule contiene la tarea 'poll-all-devices'."""
    from app.celery_app import celery_app
    from app.core.config import settings
    assert "poll-all-devices" in celery_app.conf.beat_schedule
    schedule_entry = celery_app.conf.beat_schedule["poll-all-devices"]
    assert schedule_entry["task"] == "tasks.poll_all_devices"
    assert schedule_entry["schedule"] == settings.POLL_INTERVAL_SECONDS
