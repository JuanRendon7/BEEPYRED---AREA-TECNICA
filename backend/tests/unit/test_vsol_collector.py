"""
Tests del collector SSH VSOL GPON — VSOL-01, VSOL-03, VSOL-04, VSOL-05.

Cubre:
- Registro de tasks Celery (nombres correctos)
- Circuit breaker: salta polling cuando circuit abierto (VSOL-04)
- SSH error: llama record_vsol_failure (VSOL-04)
- upsert_onu: crea Device + ONU si serial no existe
- upsert_onu: actualiza status si ONU ya existe
- upsert_onu: mapeo de estado ONLINE→UP, OFFLINE→DOWN
- Orquestador: devuelve queued=0 si no hay OLTs activas
- Orquestador: encola un task por cada OLT activa
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.device import Device, DeviceStatus, DeviceType
from app.models.onu import ONU


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_olt_device(device_id: int = 1, ip: str = "192.168.8.200") -> Device:
    d = Device()
    d.id = device_id
    d.ip_address = ip
    d.device_type = DeviceType.OLT_VSOL_GPON
    d.name = f"OLT-{device_id}"
    d.status = DeviceStatus.UP
    d.is_active = True
    return d


def _make_onu_record(device_id: int = 10, olt_id: int = 1) -> ONU:
    onu = ONU()
    onu.id = 1
    onu.device_id = device_id
    onu.olt_id = olt_id
    onu.serial_number = "4857454c12345601"
    onu.pon_port = "0/1"
    onu.onu_index = 1
    onu.onu_status = "ONLINE"
    return onu


def _make_session_for_scalars(items: list):
    """Mock de db.execute que retorna items via scalars().all()."""
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = items
    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    mock_session.execute = AsyncMock(return_value=mock_result)
    mock_session.commit = AsyncMock()
    return MagicMock(return_value=mock_session), mock_session


def _make_upsert_db_mock(existing_onu=None, existing_device=None):
    """
    Mock de db session para upsert_onu.
    Primera execute -> ONU lookup
    Segunda execute -> Device lookup (solo si ONU existe)
    """
    onu_result = MagicMock()
    onu_result.scalar_one_or_none = MagicMock(return_value=existing_onu)

    dev_result = MagicMock()
    dev_result.scalar_one_or_none = MagicMock(return_value=existing_device)

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(side_effect=[onu_result, dev_result])
    mock_db.add = MagicMock()
    mock_db.flush = AsyncMock()
    mock_db.commit = AsyncMock()
    return mock_db


# ---------------------------------------------------------------------------
# Registro de tasks Celery
# ---------------------------------------------------------------------------

def test_poll_vsol_olt_state_is_celery_task(set_test_env_vars):
    from app.tasks.vsol import poll_vsol_olt_state
    assert poll_vsol_olt_state.name == "tasks.poll_vsol_olt_state"


def test_poll_all_vsol_olts_state_is_celery_task(set_test_env_vars):
    from app.tasks.vsol import poll_all_vsol_olts_state
    assert poll_all_vsol_olts_state.name == "tasks.poll_all_vsol_olts_state"


def test_poll_vsol_olt_optical_is_celery_task(set_test_env_vars):
    from app.tasks.vsol import poll_vsol_olt_optical
    assert poll_vsol_olt_optical.name == "tasks.poll_vsol_olt_optical"


def test_poll_all_vsol_olts_optical_is_celery_task(set_test_env_vars):
    from app.tasks.vsol import poll_all_vsol_olts_optical
    assert poll_all_vsol_olts_optical.name == "tasks.poll_all_vsol_olts_optical"


# ---------------------------------------------------------------------------
# Circuit breaker — VSOL-04
# ---------------------------------------------------------------------------

def test_collect_state_skips_when_circuit_open(set_test_env_vars):
    """VSOL-04: circuit abierto → retorna skipped sin intentar SSH."""
    from app.tasks.vsol import _collect_state_async

    mock_redis = AsyncMock()
    mock_redis.aclose = AsyncMock()

    with patch("app.tasks.vsol.aioredis.from_url", return_value=mock_redis), \
         patch("app.tasks.vsol.is_vsol_circuit_open", AsyncMock(return_value=True)), \
         patch("app.tasks.vsol.asyncssh") as mock_ssh:

        result = asyncio.run(_collect_state_async(device_id=1))

    assert result["skipped"] is True
    assert result["reason"] == "circuit_open"
    mock_ssh.connect.assert_not_called()


def test_collect_optical_skips_when_circuit_open(set_test_env_vars):
    """VSOL-04: circuit abierto → optical poll también salta sin SSH."""
    from app.tasks.vsol import _collect_optical_async

    mock_redis = AsyncMock()
    mock_redis.aclose = AsyncMock()

    with patch("app.tasks.vsol.aioredis.from_url", return_value=mock_redis), \
         patch("app.tasks.vsol.is_vsol_circuit_open", AsyncMock(return_value=True)), \
         patch("app.tasks.vsol.asyncssh") as mock_ssh:

        result = asyncio.run(_collect_optical_async(device_id=1))

    assert result["skipped"] is True
    assert result["reason"] == "circuit_open"
    mock_ssh.connect.assert_not_called()


def test_circuit_checked_before_ssh_connect(set_test_env_vars):
    """VSOL-04: is_vsol_circuit_open se llama ANTES de asyncssh.connect."""
    from app.tasks.vsol import _collect_state_async

    call_order = []
    mock_redis = AsyncMock()
    mock_redis.aclose = AsyncMock()

    async def mock_circuit(redis, device_id):
        call_order.append("circuit_check")
        return True

    with patch("app.tasks.vsol.aioredis.from_url", return_value=mock_redis), \
         patch("app.tasks.vsol.is_vsol_circuit_open", side_effect=mock_circuit), \
         patch("app.tasks.vsol.asyncssh.connect") as mock_connect:

        def connect_side(*args, **kwargs):
            call_order.append("ssh_connect")
            return AsyncMock()

        mock_connect.side_effect = connect_side
        asyncio.run(_collect_state_async(device_id=1))

    assert call_order[0] == "circuit_check"
    assert "ssh_connect" not in call_order


# ---------------------------------------------------------------------------
# SSH error → record_vsol_failure — VSOL-04
# ---------------------------------------------------------------------------

def test_collect_state_records_failure_on_ssh_error(set_test_env_vars):
    """VSOL-04: error SSH → record_vsol_failure llamado al menos una vez."""
    from app.tasks.vsol import _collect_state_async

    olt = _make_olt_device()
    from app.models.device_credential import DeviceCredential
    cred = DeviceCredential()
    cred.username = "admin"
    cred.encrypted_password = b"enc"

    olt_result = MagicMock()
    olt_result.scalar_one_or_none = MagicMock(return_value=olt)
    cred_result = MagicMock()
    cred_result.scalar_one_or_none = MagicMock(return_value=cred)

    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    mock_session.execute = AsyncMock(side_effect=[olt_result, cred_result])
    mock_session.commit = AsyncMock()
    mock_db_factory = MagicMock(return_value=mock_session)

    mock_redis = AsyncMock()
    mock_redis.aclose = AsyncMock()

    record_failure = AsyncMock(return_value=False)

    with patch("app.tasks.vsol.aioredis.from_url", return_value=mock_redis), \
         patch("app.tasks.vsol.is_vsol_circuit_open", AsyncMock(return_value=False)), \
         patch("app.tasks.vsol.AsyncSessionLocal", mock_db_factory), \
         patch("app.tasks.vsol.decrypt_credential", return_value="secret"), \
         patch("app.tasks.vsol.record_vsol_failure", record_failure), \
         patch("app.tasks.vsol.asyncssh.connect", side_effect=OSError("connection refused")):

        asyncio.run(_collect_state_async(device_id=1))

    record_failure.assert_called_once_with(mock_redis, 1)


# ---------------------------------------------------------------------------
# Orquestador — _poll_all_vsol_olts_state_async
# ---------------------------------------------------------------------------

def test_poll_all_vsol_state_no_olts_returns_zero(set_test_env_vars):
    """Sin OLTs activas → {"queued": 0} sin encolar tasks."""
    from app.tasks.vsol import _poll_all_vsol_olts_state_async

    mock_factory, _ = _make_session_for_scalars([])

    with patch("app.tasks.vsol.AsyncSessionLocal", mock_factory):
        result = asyncio.run(_poll_all_vsol_olts_state_async())

    assert result == {"queued": 0}


def test_poll_all_vsol_state_queues_one_per_olt(set_test_env_vars):
    """Dos OLTs → queued=2 y poll_vsol_olt_state.delay llamado dos veces."""
    from app.tasks.vsol import _poll_all_vsol_olts_state_async

    olts = [_make_olt_device(1), _make_olt_device(2)]
    mock_factory, _ = _make_session_for_scalars(olts)

    delay_mock = MagicMock()
    with patch("app.tasks.vsol.AsyncSessionLocal", mock_factory), \
         patch("app.tasks.vsol.poll_vsol_olt_state") as task_mock:
        task_mock.delay = delay_mock
        result = asyncio.run(_poll_all_vsol_olts_state_async())

    assert result["queued"] == 2
    assert delay_mock.call_count == 2


# ---------------------------------------------------------------------------
# upsert_onu — crea Device + ONU si es nuevo
# ---------------------------------------------------------------------------

def test_upsert_onu_adds_device_and_onu_for_new_serial(set_test_env_vars):
    """ONU nueva → db.add llamado dos veces (Device + ONU) y db.commit."""
    from app.tasks.vsol import upsert_onu

    mock_db = _make_upsert_db_mock(existing_onu=None)

    asyncio.run(upsert_onu(
        mock_db,
        olt_id=1, port=1, onu_index=5,
        serial_number="4857454c12345601",
        state="ONLINE",
    ))

    assert mock_db.add.call_count == 2
    assert mock_db.flush.called
    assert mock_db.commit.called


def test_upsert_onu_new_device_type_is_onu(set_test_env_vars):
    """Device creado para ONU nueva tiene device_type=ONU."""
    from app.tasks.vsol import upsert_onu

    mock_db = _make_upsert_db_mock(existing_onu=None)
    asyncio.run(upsert_onu(
        mock_db,
        olt_id=1, port=1, onu_index=5,
        serial_number="4857454c12345601",
        state="ONLINE",
    ))

    # Primer add es el Device
    first_add_arg = mock_db.add.call_args_list[0][0][0]
    assert isinstance(first_add_arg, Device)
    assert first_add_arg.device_type == DeviceType.ONU
    assert first_add_arg.ip_address == "0.0.0.0"


def test_upsert_onu_new_onu_has_correct_serial(set_test_env_vars):
    """ONU creada almacena serial_number y onu_index correctos."""
    from app.tasks.vsol import upsert_onu

    mock_db = _make_upsert_db_mock(existing_onu=None)
    asyncio.run(upsert_onu(
        mock_db,
        olt_id=1, port=1, onu_index=5,
        serial_number="ABCDEF1234567890",
        state="OFFLINE",
    ))

    # Segundo add es la ONU
    second_add_arg = mock_db.add.call_args_list[1][0][0]
    assert isinstance(second_add_arg, ONU)
    assert second_add_arg.serial_number == "ABCDEF1234567890"
    assert second_add_arg.onu_index == 5
    assert second_add_arg.onu_status == "OFFLINE"


# ---------------------------------------------------------------------------
# upsert_onu — actualiza ONU existente
# ---------------------------------------------------------------------------

def test_upsert_onu_updates_status_for_existing(set_test_env_vars):
    """ONU existente → onu_status actualizado, sin add() extra."""
    from app.tasks.vsol import upsert_onu

    existing_onu = _make_onu_record()
    existing_device = _make_olt_device()
    existing_device.device_type = DeviceType.ONU

    mock_db = _make_upsert_db_mock(existing_onu=existing_onu, existing_device=existing_device)

    asyncio.run(upsert_onu(
        mock_db,
        olt_id=1, port=1, onu_index=1,
        serial_number="4857454c12345601",
        state="OFFLINE",
    ))

    assert existing_onu.onu_status == "OFFLINE"
    assert mock_db.add.call_count == 0
    assert mock_db.commit.called


def test_upsert_onu_online_sets_device_status_up(set_test_env_vars):
    """Estado ONLINE → Device.status = UP."""
    from app.tasks.vsol import upsert_onu

    existing_onu = _make_onu_record()
    existing_device = _make_olt_device()
    existing_device.device_type = DeviceType.ONU
    existing_device.status = DeviceStatus.DOWN

    mock_db = _make_upsert_db_mock(existing_onu=existing_onu, existing_device=existing_device)

    asyncio.run(upsert_onu(
        mock_db,
        olt_id=1, port=1, onu_index=1,
        serial_number="4857454c12345601",
        state="ONLINE",
    ))

    assert existing_device.status == DeviceStatus.UP


def test_upsert_onu_offline_sets_device_status_down(set_test_env_vars):
    """Estado OFFLINE → Device.status = DOWN."""
    from app.tasks.vsol import upsert_onu

    existing_onu = _make_onu_record()
    existing_device = _make_olt_device()
    existing_device.device_type = DeviceType.ONU
    existing_device.status = DeviceStatus.UP

    mock_db = _make_upsert_db_mock(existing_onu=existing_onu, existing_device=existing_device)

    asyncio.run(upsert_onu(
        mock_db,
        olt_id=1, port=1, onu_index=1,
        serial_number="4857454c12345601",
        state="OFFLINE",
    ))

    assert existing_device.status == DeviceStatus.DOWN
