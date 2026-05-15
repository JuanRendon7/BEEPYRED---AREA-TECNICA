"""
Tests para vsol_circuit_breaker.py — VSOL-04.

Verifica que el circuit breaker usa el prefijo 'vsol:' (separado de 'cb:' de Mikrotik)
y que abre tras 3 fallos, se resetea con success, y retorna True/False correctamente.
"""
from unittest.mock import AsyncMock, MagicMock
import pytest

from app.services.vsol_circuit_breaker import (
    CIRCUIT_FAIL_THRESHOLD,
    CIRCUIT_OPEN_TTL,
    is_vsol_circuit_open,
    record_vsol_failure,
    record_vsol_success,
)


@pytest.fixture
def redis_mock():
    mock = AsyncMock()
    mock.exists = AsyncMock(return_value=0)
    mock.incr = AsyncMock(return_value=1)
    mock.expire = AsyncMock(return_value=True)
    mock.setex = AsyncMock(return_value=True)
    mock.delete = AsyncMock(return_value=1)
    return mock


class TestIsVsolCircuitOpen:
    async def test_returns_false_when_key_not_exists(self, redis_mock):
        redis_mock.exists = AsyncMock(return_value=0)
        result = await is_vsol_circuit_open(redis_mock, device_id=99)
        assert result is False

    async def test_returns_true_when_key_exists(self, redis_mock):
        redis_mock.exists = AsyncMock(return_value=1)
        result = await is_vsol_circuit_open(redis_mock, device_id=99)
        assert result is True

    async def test_uses_vsol_prefix_not_cb(self, redis_mock):
        redis_mock.exists = AsyncMock(return_value=0)
        await is_vsol_circuit_open(redis_mock, device_id=42)
        call_args = redis_mock.exists.call_args[0][0]
        assert call_args.startswith("vsol:"), f"Clave debe empezar con 'vsol:', no '{call_args}'"
        assert not call_args.startswith("cb:"), "No debe usar prefijo 'cb:' (es de Mikrotik)"


class TestRecordVsolFailure:
    async def test_does_not_open_circuit_before_threshold(self, redis_mock):
        redis_mock.incr = AsyncMock(return_value=1)
        result = await record_vsol_failure(redis_mock, device_id=1)
        assert result is False
        redis_mock.setex.assert_not_called()

    async def test_opens_circuit_at_threshold(self, redis_mock):
        redis_mock.incr = AsyncMock(return_value=CIRCUIT_FAIL_THRESHOLD)
        result = await record_vsol_failure(redis_mock, device_id=1)
        assert result is True
        redis_mock.setex.assert_called_once()

    async def test_setex_uses_vsol_open_key(self, redis_mock):
        redis_mock.incr = AsyncMock(return_value=CIRCUIT_FAIL_THRESHOLD)
        await record_vsol_failure(redis_mock, device_id=7)
        open_key = redis_mock.setex.call_args[0][0]
        assert "vsol:" in open_key
        assert "7" in open_key

    async def test_setex_uses_correct_ttl(self, redis_mock):
        redis_mock.incr = AsyncMock(return_value=CIRCUIT_FAIL_THRESHOLD)
        await record_vsol_failure(redis_mock, device_id=1)
        ttl = redis_mock.setex.call_args[0][1]
        assert ttl == CIRCUIT_OPEN_TTL

    async def test_deletes_fails_key_when_circuit_opens(self, redis_mock):
        redis_mock.incr = AsyncMock(return_value=CIRCUIT_FAIL_THRESHOLD)
        await record_vsol_failure(redis_mock, device_id=1)
        redis_mock.delete.assert_called_once()
        deleted_key = redis_mock.delete.call_args[0][0]
        assert "vsol:fails:1" == deleted_key

    async def test_expire_called_on_fails_key(self, redis_mock):
        redis_mock.incr = AsyncMock(return_value=1)
        await record_vsol_failure(redis_mock, device_id=5)
        redis_mock.expire.assert_called_once()
        expired_key = redis_mock.expire.call_args[0][0]
        assert expired_key == "vsol:fails:5"


class TestRecordVsolSuccess:
    async def test_deletes_open_and_fails_keys(self, redis_mock):
        await record_vsol_success(redis_mock, device_id=3)
        assert redis_mock.delete.call_count == 2

    async def test_deletes_vsol_prefixed_keys(self, redis_mock):
        await record_vsol_success(redis_mock, device_id=3)
        deleted_keys = {call[0][0] for call in redis_mock.delete.call_args_list}
        assert "vsol:fails:3" in deleted_keys
        assert "vsol:open:3" in deleted_keys

    async def test_no_cb_keys_deleted(self, redis_mock):
        await record_vsol_success(redis_mock, device_id=3)
        deleted_keys = [call[0][0] for call in redis_mock.delete.call_args_list]
        for key in deleted_keys:
            assert not key.startswith("cb:"), f"No debe borrar claves cb:, borro '{key}'"
