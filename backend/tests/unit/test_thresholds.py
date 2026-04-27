"""
Tests del servicio de umbrales de alerta configurables — ALERT-06.

Comportamientos verificados:
- get_threshold("cpu_high", device_id=5) retorna umbral especifico de DB si existe
- get_threshold("cpu_high", device_id=5) retorna umbral global si no hay especifico
- get_threshold("cpu_high") retorna settings.CPU_ALERT_THRESHOLD_PCT como fallback
- get_threshold("signal_low") retorna settings.ONU_SIGNAL_MIN_DBM como fallback
- get_threshold("tipo_inexistente") retorna None
"""
import asyncio
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers para construir resultados mock de DB
# ---------------------------------------------------------------------------

def _make_scalar_result(value):
    """Crea un mock de result.scalar_one_or_none() que retorna value."""
    result = MagicMock()
    result.scalar_one_or_none = MagicMock(return_value=value)
    return result


# ---------------------------------------------------------------------------
# Tests de get_threshold
# ---------------------------------------------------------------------------

def test_get_threshold_returns_device_specific_from_db(set_test_env_vars):
    """ALERT-06: get_threshold retorna umbral device-especifico cuando existe en DB."""
    from app.services.thresholds import get_threshold

    # Primera query (device-especifico) retorna un valor
    device_specific_result = _make_scalar_result(Decimal("85.0"))

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=device_specific_result)

    result = asyncio.run(get_threshold(mock_session, "cpu_high", device_id=5))

    assert result == 85.0
    assert isinstance(result, float)
    # Solo se debe hacer 1 query (la device-especifica)
    assert mock_session.execute.call_count == 1


def test_get_threshold_falls_back_to_global_when_no_device_specific(set_test_env_vars):
    """ALERT-06: get_threshold retorna umbral global cuando no hay device-especifico."""
    from app.services.thresholds import get_threshold

    # Primera query (device-especifico) no retorna nada
    # Segunda query (global) retorna un valor
    device_result = _make_scalar_result(None)
    global_result = _make_scalar_result(Decimal("95.0"))

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(side_effect=[device_result, global_result])

    result = asyncio.run(get_threshold(mock_session, "cpu_high", device_id=5))

    assert result == 95.0
    assert mock_session.execute.call_count == 2


def test_get_threshold_falls_back_to_env_var_when_no_db(set_test_env_vars):
    """ALERT-06: get_threshold retorna settings.CPU_ALERT_THRESHOLD_PCT cuando no hay fila en DB."""
    from app.services.thresholds import get_threshold
    from app.core.config import settings

    # Ambas queries retornan None
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=_make_scalar_result(None))

    result = asyncio.run(get_threshold(mock_session, "cpu_high", device_id=5))

    assert result == settings.CPU_ALERT_THRESHOLD_PCT


def test_get_threshold_signal_low_falls_back_to_env_var(set_test_env_vars):
    """ALERT-06: get_threshold retorna settings.ONU_SIGNAL_MIN_DBM como fallback para signal_low."""
    from app.services.thresholds import get_threshold
    from app.core.config import settings

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=_make_scalar_result(None))

    result = asyncio.run(get_threshold(mock_session, "signal_low"))

    assert result == settings.ONU_SIGNAL_MIN_DBM


def test_get_threshold_no_device_id_skips_device_query(set_test_env_vars):
    """ALERT-06: get_threshold sin device_id no hace query device-especifica."""
    from app.services.thresholds import get_threshold

    global_result = _make_scalar_result(Decimal("90.0"))
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=global_result)

    result = asyncio.run(get_threshold(mock_session, "cpu_high"))

    assert result == 90.0
    # Solo 1 query: la global (no la device-especifica)
    assert mock_session.execute.call_count == 1


def test_get_threshold_returns_none_for_unknown_type(set_test_env_vars):
    """ALERT-06: get_threshold retorna None para tipos de alerta sin fallback en settings."""
    from app.services.thresholds import get_threshold

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=_make_scalar_result(None))

    result = asyncio.run(get_threshold(mock_session, "tipo_inexistente"))

    assert result is None


def test_get_threshold_priority_device_specific_over_global(set_test_env_vars):
    """ALERT-06: umbral device-especifico tiene prioridad sobre global."""
    from app.services.thresholds import get_threshold

    device_result = _make_scalar_result(Decimal("75.0"))

    mock_session = AsyncMock()
    # Solo la primera query debe ser llamada
    mock_session.execute = AsyncMock(return_value=device_result)

    result = asyncio.run(get_threshold(mock_session, "cpu_high", device_id=1))

    assert result == 75.0
    # Si hay device-especifico, no se debe consultar el global
    assert mock_session.execute.call_count == 1
