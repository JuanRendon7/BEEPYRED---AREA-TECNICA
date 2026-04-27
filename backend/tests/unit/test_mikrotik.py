"""
Tests del collector RouterOS API para Mikrotik — MK-01, MK-02, MK-03, MK-04.

CRITICO: estos tests NO conectan a hardware real.
Usan unittest.mock para aislar:
- librouteros.async_connect: patched para retornar api mock
- redis.asyncio: AsyncMock
- AsyncSessionLocal: MagicMock con context manager async
"""
import asyncio
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from app.models.device import Device, DeviceStatus, DeviceType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_api_mock(resource_items=None, interface_items=None):
    """
    Construye un mock del objeto api de librouteros.

    api.path("system", "resource") retorna un async iterable de resource_items.
    api.path("interface") retorna un async iterable de interface_items.
    api.close() es llamable de forma sincronica.
    """
    if resource_items is None:
        resource_items = [
            {
                "cpu-load": 45,
                "free-memory": 52428800,
                "total-memory": 134217728,
            }
        ]
    if interface_items is None:
        interface_items = [
            {
                "name": "ether1",
                "tx-bits-per-second": 1000000,
                "rx-bits-per-second": 500000,
            }
        ]

    async def _async_iter(items):
        for item in items:
            yield item

    def _make_path_mock(items):
        path_mock = MagicMock()
        path_mock.__aiter__ = MagicMock(return_value=_async_iter(items).__aiter__())
        return path_mock

    api = MagicMock()
    api.close = MagicMock()

    def _path_selector(*args):
        if args == ("system", "resource"):
            return _make_path_mock(resource_items)
        elif args == ("interface",):
            return _make_path_mock(interface_items)
        return _make_path_mock([])

    api.path = MagicMock(side_effect=_path_selector)
    return api


def _make_db_session_mock(device=None, credential=None):
    """Construye un mock de AsyncSessionLocal con context manager."""
    mock_dev_result = MagicMock()
    mock_dev_result.scalar_one_or_none = MagicMock(return_value=device)

    mock_cred_result = MagicMock()
    mock_cred_result.scalar_one_or_none = MagicMock(return_value=credential)

    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    mock_session.execute = AsyncMock(side_effect=[mock_dev_result, mock_cred_result])
    mock_session.commit = AsyncMock()

    mock_factory = MagicMock()
    mock_factory.return_value = mock_session
    return mock_factory, mock_session


def _make_device(device_id=1, ip="192.168.1.1"):
    """Crea un Device fixture tipo MIKROTIK."""
    d = Device()
    d.id = device_id
    d.ip_address = ip
    d.device_type = DeviceType.MIKROTIK
    d.name = f"mikrotik-{device_id}"
    d.status = DeviceStatus.UP
    d.is_active = True
    return d


def _make_credential(device_id=1, username="admin", password_enc="encrypted_pass"):
    """Crea un DeviceCredential fixture para routeros_api."""
    from app.models.device_credential import DeviceCredential
    cred = DeviceCredential()
    cred.id = 1
    cred.device_id = device_id
    cred.credential_type = "routeros_api"
    cred.username = username
    cred.encrypted_password = password_enc
    return cred


# ---------------------------------------------------------------------------
# Tests de registro del task Celery
# ---------------------------------------------------------------------------

def test_poll_mikrotik_device_is_registered_celery_task(set_test_env_vars):
    """MK-01: poll_mikrotik_device es un Celery task con name='tasks.poll_mikrotik_device'."""
    from app.tasks.mikrotik import poll_mikrotik_device
    assert poll_mikrotik_device.name == "tasks.poll_mikrotik_device"


# ---------------------------------------------------------------------------
# Tests de circuit breaker (MK-04)
# ---------------------------------------------------------------------------

def test_poll_mikrotik_device_skips_when_circuit_open(set_test_env_vars):
    """MK-04: cuando el circuit breaker esta abierto, retorna skipped sin llamar async_connect."""
    from app.tasks.mikrotik import _collect_mikrotik_async

    mock_redis = AsyncMock()
    mock_redis.aclose = AsyncMock()

    with patch("app.tasks.mikrotik.aioredis.from_url", return_value=mock_redis), \
         patch("app.tasks.mikrotik.is_circuit_open", new_callable=AsyncMock, return_value=True), \
         patch("app.tasks.mikrotik.async_connect") as mock_connect:

        result = asyncio.run(_collect_mikrotik_async(device_id=1))

    assert result["skipped"] is True
    assert result["reason"] == "circuit_open"
    mock_connect.assert_not_called()


def test_poll_mikrotik_device_checks_circuit_before_connecting(set_test_env_vars):
    """MK-04: is_circuit_open() se verifica ANTES de llamar async_connect."""
    from app.tasks.mikrotik import _collect_mikrotik_async

    call_order = []

    mock_redis = AsyncMock()
    mock_redis.aclose = AsyncMock()

    async def mock_circuit_check(redis, device_id):
        call_order.append("is_circuit_open")
        return True  # circuit abierto — para el test en is_circuit_open

    with patch("app.tasks.mikrotik.aioredis.from_url", return_value=mock_redis), \
         patch("app.tasks.mikrotik.is_circuit_open", side_effect=mock_circuit_check), \
         patch("app.tasks.mikrotik.async_connect") as mock_connect:

        def connect_side_effect(*args, **kwargs):
            call_order.append("async_connect")
            return AsyncMock()

        mock_connect.side_effect = connect_side_effect
        asyncio.run(_collect_mikrotik_async(device_id=1))

    # is_circuit_open debe ser el primero en la lista de llamadas
    assert call_order[0] == "is_circuit_open"
    assert "async_connect" not in call_order


# ---------------------------------------------------------------------------
# Tests de recoleccion de metricas (MK-01, MK-02)
# ---------------------------------------------------------------------------

def test_collect_calls_system_resource_path(set_test_env_vars):
    """MK-01: _collect llama api.path('system', 'resource') para CPU y RAM."""
    from app.tasks.mikrotik import _fetch_routeros_data

    api_mock = _make_api_mock()

    async def fake_connect(**kwargs):
        return api_mock

    mock_redis = AsyncMock()

    with patch("app.tasks.mikrotik.async_connect", side_effect=fake_connect):
        result = asyncio.run(
            _fetch_routeros_data("192.168.1.1", "admin", "pass", 1, mock_redis)
        )

    api_mock.path.assert_any_call("system", "resource")
    assert result is not None


def test_collect_calls_interface_path(set_test_env_vars):
    """MK-02: _collect llama api.path('interface') para trafico TX/RX."""
    from app.tasks.mikrotik import _fetch_routeros_data

    api_mock = _make_api_mock()

    async def fake_connect(**kwargs):
        return api_mock

    mock_redis = AsyncMock()

    with patch("app.tasks.mikrotik.async_connect", side_effect=fake_connect):
        result = asyncio.run(
            _fetch_routeros_data("192.168.1.1", "admin", "pass", 1, mock_redis)
        )

    api_mock.path.assert_any_call("interface")


def test_parse_metrics_cpu_pct_calculated_correctly(set_test_env_vars):
    """MK-01: cpu_pct se obtiene directamente del campo 'cpu-load' (ya es porcentaje)."""
    from app.tasks.mikrotik import _parse_metrics

    raw = {
        "resource": {"cpu-load": 45, "free-memory": 52428800, "total-memory": 134217728},
        "interfaces": [],
    }

    metrics = _parse_metrics(raw)

    cpu_metrics = [m for m in metrics if m["metric_name"] == "cpu_pct"]
    assert len(cpu_metrics) == 1
    assert cpu_metrics[0]["value"] == 45.0
    assert cpu_metrics[0]["unit"] == "%"
    assert cpu_metrics[0]["interface"] is None


def test_parse_metrics_ram_pct_calculated_correctly(set_test_env_vars):
    """MK-01: ram_pct = (1 - free_memory/total_memory) * 100."""
    from app.tasks.mikrotik import _parse_metrics

    free_mem = 33554432   # 32 MB
    total_mem = 134217728  # 128 MB
    expected_ram_pct = round((1.0 - free_mem / total_mem) * 100.0, 2)  # 75.0

    raw = {
        "resource": {
            "cpu-load": 10,
            "free-memory": free_mem,
            "total-memory": total_mem,
        },
        "interfaces": [],
    }

    metrics = _parse_metrics(raw)

    ram_metrics = [m for m in metrics if m["metric_name"] == "ram_pct"]
    assert len(ram_metrics) == 1
    assert ram_metrics[0]["value"] == expected_ram_pct
    assert ram_metrics[0]["unit"] == "%"


def test_parse_metrics_tx_bps_per_interface(set_test_env_vars):
    """MK-02: cada interfaz con tx-bits-per-second genera metrica tx_bps."""
    from app.tasks.mikrotik import _parse_metrics

    raw = {
        "resource": {},
        "interfaces": [
            {"name": "ether1", "tx-bits-per-second": 1000000, "rx-bits-per-second": 500000},
            {"name": "wlan1", "tx-bits-per-second": 2000000, "rx-bits-per-second": 800000},
        ],
    }

    metrics = _parse_metrics(raw)

    tx_metrics = [m for m in metrics if m["metric_name"] == "tx_bps"]
    assert len(tx_metrics) == 2
    tx_names = {m["interface"] for m in tx_metrics}
    assert "ether1" in tx_names
    assert "wlan1" in tx_names


def test_parse_metrics_rx_bps_per_interface(set_test_env_vars):
    """MK-02: cada interfaz con rx-bits-per-second genera metrica rx_bps."""
    from app.tasks.mikrotik import _parse_metrics

    raw = {
        "resource": {},
        "interfaces": [
            {"name": "ether1", "tx-bits-per-second": 1000000, "rx-bits-per-second": 500000},
        ],
    }

    metrics = _parse_metrics(raw)

    rx_metrics = [m for m in metrics if m["metric_name"] == "rx_bps"]
    assert len(rx_metrics) == 1
    assert rx_metrics[0]["interface"] == "ether1"
    assert rx_metrics[0]["value"] == 500000.0
    assert rx_metrics[0]["unit"] == "bps"


def test_parse_metrics_handles_missing_fields_without_keyerror(set_test_env_vars):
    """MK-01: campos RouterOS ausentes se manejan con .get() sin lanzar KeyError."""
    from app.tasks.mikrotik import _parse_metrics

    # resource completamente vacio — sin cpu-load, sin memory fields
    raw = {
        "resource": {},
        "interfaces": [
            {"name": "ether1"},  # sin tx/rx-bits-per-second
        ],
    }

    # No debe lanzar KeyError
    metrics = _parse_metrics(raw)
    assert isinstance(metrics, list)
    # Sin datos validos, la lista debe estar vacia
    assert len(metrics) == 0


def test_parse_metrics_skips_interface_without_name(set_test_env_vars):
    """MK-02: interfaces sin campo 'name' se omiten silenciosamente."""
    from app.tasks.mikrotik import _parse_metrics

    raw = {
        "resource": {},
        "interfaces": [
            {"tx-bits-per-second": 1000, "rx-bits-per-second": 500},  # sin name
        ],
    }

    metrics = _parse_metrics(raw)
    assert len(metrics) == 0


# ---------------------------------------------------------------------------
# Tests de escritura de metricas (MK-03)
# ---------------------------------------------------------------------------

def test_write_metrics_uses_insert_metric(set_test_env_vars):
    """MK-03: _write_metrics usa insert(Metric) con lista de dicts."""
    from app.tasks.mikrotik import _write_metrics
    from app.models.metric import Metric
    from sqlalchemy import insert

    metrics = [
        {"metric_name": "cpu_pct", "value": 45.0, "unit": "%", "interface": None,
         "recorded_at": None},
    ]

    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    mock_session.execute = AsyncMock()
    mock_session.commit = AsyncMock()

    mock_factory = MagicMock()
    mock_factory.return_value = mock_session

    with patch("app.tasks.mikrotik.AsyncSessionLocal", mock_factory), \
         patch("app.tasks.mikrotik.insert") as mock_insert:
        mock_insert.return_value = MagicMock()
        asyncio.run(_write_metrics(device_id=1, metrics=metrics))

    mock_insert.assert_called_once_with(Metric)
    mock_session.commit.assert_called_once()


def test_write_metrics_does_nothing_if_empty(set_test_env_vars):
    """MK-03: _write_metrics no ejecuta query si la lista esta vacia."""
    from app.tasks.mikrotik import _write_metrics

    mock_session = AsyncMock()
    mock_factory = MagicMock()
    mock_factory.return_value = mock_session

    with patch("app.tasks.mikrotik.AsyncSessionLocal", mock_factory):
        asyncio.run(_write_metrics(device_id=1, metrics=[]))

    mock_session.execute.assert_not_called()


# ---------------------------------------------------------------------------
# Tests de api.close() en finally (MK-03)
# ---------------------------------------------------------------------------

def test_api_close_called_in_finally_on_success(set_test_env_vars):
    """MK-03: api.close() se llama en finally aunque la recoleccion sea exitosa."""
    from app.tasks.mikrotik import _fetch_routeros_data

    api_mock = _make_api_mock()

    async def fake_connect(**kwargs):
        return api_mock

    mock_redis = AsyncMock()

    with patch("app.tasks.mikrotik.async_connect", side_effect=fake_connect):
        asyncio.run(_fetch_routeros_data("192.168.1.1", "admin", "pass", 1, mock_redis))

    api_mock.close.assert_called_once()


def test_api_close_called_in_finally_on_error(set_test_env_vars):
    """MK-03: api.close() se llama en finally aunque falle la recoleccion post-conexion."""
    from app.tasks.mikrotik import _fetch_routeros_data

    api_mock = _make_api_mock()

    # La path falla despues de conectar
    def _failing_path(*args):
        raise RuntimeError("RouterOS path error")

    api_mock.path = MagicMock(side_effect=_failing_path)

    async def fake_connect(**kwargs):
        return api_mock

    mock_redis = AsyncMock()
    mock_redis.incr = AsyncMock(return_value=1)
    mock_redis.expire = AsyncMock()

    with patch("app.tasks.mikrotik.async_connect", side_effect=fake_connect), \
         patch("app.tasks.mikrotik.record_api_failure", new_callable=AsyncMock, return_value=False):
        result = asyncio.run(
            _fetch_routeros_data("192.168.1.1", "admin", "pass", 1, mock_redis)
        )

    api_mock.close.assert_called_once()
    assert result is None  # error — retorna None


def test_api_close_not_called_if_connect_fails(set_test_env_vars):
    """MK-03: api.close() NO se llama si async_connect falla (api es None)."""
    from app.tasks.mikrotik import _fetch_routeros_data

    async def failing_connect(**kwargs):
        raise ConnectionRefusedError("Connection refused")

    mock_redis = AsyncMock()
    mock_redis.incr = AsyncMock(return_value=1)
    mock_redis.expire = AsyncMock()

    with patch("app.tasks.mikrotik.async_connect", side_effect=failing_connect), \
         patch("app.tasks.mikrotik.record_api_failure", new_callable=AsyncMock, return_value=False):
        result = asyncio.run(
            _fetch_routeros_data("192.168.1.1", "admin", "pass", 1, mock_redis)
        )

    # No lanza excepcion, retorna None
    assert result is None


# ---------------------------------------------------------------------------
# Tests de circuit breaker en caso de fallo RouterOS (MK-04)
# ---------------------------------------------------------------------------

def test_record_api_failure_called_on_routeros_error(set_test_env_vars):
    """MK-04: record_api_failure() se llama cuando async_connect lanza excepcion."""
    from app.tasks.mikrotik import _fetch_routeros_data

    async def failing_connect(**kwargs):
        raise ConnectionRefusedError("Cannot connect")

    mock_redis = AsyncMock()

    with patch("app.tasks.mikrotik.async_connect", side_effect=failing_connect), \
         patch("app.tasks.mikrotik.record_api_failure", new_callable=AsyncMock) as mock_failure:
        mock_failure.return_value = False
        asyncio.run(_fetch_routeros_data("192.168.1.1", "admin", "pass", 5, mock_redis))

    mock_failure.assert_called_once_with(mock_redis, 5)


def test_record_api_success_called_on_successful_collect(set_test_env_vars):
    """MK-04: record_api_success() se llama cuando la recoleccion es exitosa."""
    from app.tasks.mikrotik import _collect_mikrotik_async
    from app.models.device_credential import DeviceCredential

    device = _make_device(device_id=3)
    cred = _make_credential(device_id=3)

    mock_factory, mock_session = _make_db_session_mock(device=device, credential=cred)
    api_mock = _make_api_mock()

    async def fake_connect(**kwargs):
        return api_mock

    mock_redis = AsyncMock()
    mock_redis.aclose = AsyncMock()

    with patch("app.tasks.mikrotik.aioredis.from_url", return_value=mock_redis), \
         patch("app.tasks.mikrotik.is_circuit_open", new_callable=AsyncMock, return_value=False), \
         patch("app.tasks.mikrotik.AsyncSessionLocal", mock_factory), \
         patch("app.tasks.mikrotik.async_connect", side_effect=fake_connect), \
         patch("app.tasks.mikrotik.record_api_success", new_callable=AsyncMock) as mock_success, \
         patch("app.tasks.mikrotik._write_metrics", new_callable=AsyncMock), \
         patch("app.tasks.mikrotik.decrypt_credential", return_value="plainpassword"):

        asyncio.run(_collect_mikrotik_async(device_id=3))

    mock_success.assert_called_once_with(mock_redis, 3)
