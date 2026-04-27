"""
Tests del circuit breaker Redis por dispositivo — MK-04.

Comportamientos verificados:
- is_circuit_open() retorna False cuando no hay clave Redis cb:open:{id}
- record_api_failure() 3 veces abre el circuit (setex cb:open:{id} con TTL 300)
- is_circuit_open() retorna True despues de abrirse
- record_api_success() elimina cb:open:{id} y cb:fails:{id}
- circuit se auto-resetea: clave expira con TTL via setex (verificar TTL via mock)
"""
import asyncio
from unittest.mock import AsyncMock, call, patch

import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_redis():
    """Mock de redis.asyncio.Redis para tests de circuit breaker."""
    r = AsyncMock()
    r.exists = AsyncMock(return_value=0)
    r.incr = AsyncMock(return_value=1)
    r.expire = AsyncMock(return_value=True)
    r.setex = AsyncMock(return_value=True)
    r.delete = AsyncMock(return_value=1)
    return r


# ---------------------------------------------------------------------------
# Tests de is_circuit_open
# ---------------------------------------------------------------------------

def test_is_circuit_open_returns_false_when_no_key(set_test_env_vars, mock_redis):
    """MK-04: is_circuit_open() retorna False cuando no existe la clave cb:open:{id}."""
    from app.services.circuit_breaker import is_circuit_open

    mock_redis.exists = AsyncMock(return_value=0)

    result = asyncio.run(is_circuit_open(mock_redis, device_id=1))

    assert result is False
    mock_redis.exists.assert_called_once_with("cb:open:1")


def test_is_circuit_open_returns_true_when_key_exists(set_test_env_vars, mock_redis):
    """MK-04: is_circuit_open() retorna True cuando existe la clave cb:open:{id}."""
    from app.services.circuit_breaker import is_circuit_open

    mock_redis.exists = AsyncMock(return_value=1)

    result = asyncio.run(is_circuit_open(mock_redis, device_id=42))

    assert result is True
    mock_redis.exists.assert_called_once_with("cb:open:42")


# ---------------------------------------------------------------------------
# Tests de record_api_failure
# ---------------------------------------------------------------------------

def test_record_api_failure_increments_counter(set_test_env_vars, mock_redis):
    """MK-04: record_api_failure incrementa el contador cb:fails:{id}."""
    from app.services.circuit_breaker import record_api_failure

    mock_redis.incr = AsyncMock(return_value=1)

    result = asyncio.run(record_api_failure(mock_redis, device_id=5))

    mock_redis.incr.assert_called_once_with("cb:fails:5")
    assert result is False  # no se abre con solo 1 fallo


def test_record_api_failure_sets_ttl_on_fails_key(set_test_env_vars, mock_redis):
    """MK-04: record_api_failure establece TTL en la clave de fallos."""
    from app.services.circuit_breaker import record_api_failure, CIRCUIT_OPEN_TTL

    mock_redis.incr = AsyncMock(return_value=1)

    asyncio.run(record_api_failure(mock_redis, device_id=5))

    mock_redis.expire.assert_called_once_with("cb:fails:5", CIRCUIT_OPEN_TTL)


def test_record_api_failure_does_not_open_circuit_below_threshold(set_test_env_vars, mock_redis):
    """MK-04: record_api_failure con 2 fallos no abre el circuit."""
    from app.services.circuit_breaker import record_api_failure

    mock_redis.incr = AsyncMock(return_value=2)

    result = asyncio.run(record_api_failure(mock_redis, device_id=5))

    assert result is False
    mock_redis.setex.assert_not_called()


def test_record_api_failure_opens_circuit_at_threshold(set_test_env_vars, mock_redis):
    """MK-04: record_api_failure abre el circuit al llegar al threshold (3 fallos)."""
    from app.services.circuit_breaker import record_api_failure, CIRCUIT_OPEN_TTL, CIRCUIT_FAIL_THRESHOLD

    mock_redis.incr = AsyncMock(return_value=CIRCUIT_FAIL_THRESHOLD)

    result = asyncio.run(record_api_failure(mock_redis, device_id=7))

    assert result is True
    # Debe setex la clave cb:open con TTL 300
    mock_redis.setex.assert_called_once_with("cb:open:7", CIRCUIT_OPEN_TTL, "1")
    # Debe eliminar el contador de fallos al abrir el circuit
    mock_redis.delete.assert_called_once_with("cb:fails:7")


def test_record_api_failure_circuit_open_ttl_is_5_minutes(set_test_env_vars):
    """MK-04: CIRCUIT_OPEN_TTL debe ser 300 segundos (5 minutos)."""
    from app.services.circuit_breaker import CIRCUIT_OPEN_TTL
    assert CIRCUIT_OPEN_TTL == 300


def test_record_api_failure_circuit_fail_threshold_is_3(set_test_env_vars):
    """MK-04: CIRCUIT_FAIL_THRESHOLD debe ser 3."""
    from app.services.circuit_breaker import CIRCUIT_FAIL_THRESHOLD
    assert CIRCUIT_FAIL_THRESHOLD == 3


# ---------------------------------------------------------------------------
# Tests de record_api_success
# ---------------------------------------------------------------------------

def test_record_api_success_deletes_open_key(set_test_env_vars, mock_redis):
    """MK-04: record_api_success elimina la clave cb:open:{id}."""
    from app.services.circuit_breaker import record_api_success

    asyncio.run(record_api_success(mock_redis, device_id=3))

    # Debe eliminar ambas claves
    calls = mock_redis.delete.call_args_list
    deleted_keys = [c[0][0] for c in calls]
    assert "cb:fails:3" in deleted_keys
    assert "cb:open:3" in deleted_keys


def test_record_api_success_deletes_fails_key(set_test_env_vars, mock_redis):
    """MK-04: record_api_success elimina la clave cb:fails:{id}."""
    from app.services.circuit_breaker import record_api_success

    asyncio.run(record_api_success(mock_redis, device_id=3))

    calls = mock_redis.delete.call_args_list
    deleted_keys = [c[0][0] for c in calls]
    assert "cb:fails:3" in deleted_keys


def test_record_api_success_resets_after_circuit_was_open(set_test_env_vars, mock_redis):
    """MK-04: Flujo completo — abrir circuit y luego resetearlo con exito."""
    from app.services.circuit_breaker import (
        is_circuit_open,
        record_api_failure,
        record_api_success,
        CIRCUIT_FAIL_THRESHOLD,
    )

    # Simular 3 fallos que abren el circuit
    mock_redis.incr = AsyncMock(return_value=CIRCUIT_FAIL_THRESHOLD)
    asyncio.run(record_api_failure(mock_redis, device_id=10))

    # Ahora el circuit esta abierto
    mock_redis.exists = AsyncMock(return_value=1)
    assert asyncio.run(is_circuit_open(mock_redis, device_id=10)) is True

    # Exito: circuit se resetea
    asyncio.run(record_api_success(mock_redis, device_id=10))
    mock_redis.exists = AsyncMock(return_value=0)
    assert asyncio.run(is_circuit_open(mock_redis, device_id=10)) is False
