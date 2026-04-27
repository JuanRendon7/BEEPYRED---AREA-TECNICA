"""
Tests de la tarea Celery de limpieza de datos historicos — INC-04, MK-03.

Cubre:
- cleanup_old_data() es un Celery task con name="tasks.cleanup_old_data"
- DELETE en metrics WHERE recorded_at < NOW() - INTERVAL '30 days'
- DELETE en incidents WHERE resolved_at IS NOT NULL AND resolved_at < NOW() - INTERVAL '30 days'
- NO elimina incidentes con resolved_at IS NULL (incidentes abiertos)
- Retorna dict con metrics_deleted e incidents_deleted
- beat_schedule tiene "cleanup-old-data" con crontab(hour=3, minute=0)

CRITICO: No conecta a PostgreSQL real.
Usa AsyncMock para simular AsyncSessionLocal.
"""
import asyncio
import inspect
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_execute_result(rowcount=0):
    """Simula resultado de db.execute() con .rowcount."""
    result = MagicMock()
    result.rowcount = rowcount
    return result


def make_mock_db_session(metrics_rowcount=5, incidents_rowcount=3):
    """
    Construye un mock de AsyncSession que retorna rowcounts para
    las dos operaciones DELETE (metrics y incidents).
    """
    metrics_result = make_execute_result(rowcount=metrics_rowcount)
    incidents_result = make_execute_result(rowcount=incidents_rowcount)

    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    mock_session.execute = AsyncMock(
        side_effect=[metrics_result, incidents_result]
    )
    mock_session.commit = AsyncMock()

    mock_factory = MagicMock(return_value=mock_session)
    return mock_factory, mock_session


# ---------------------------------------------------------------------------
# Tests del Celery task
# ---------------------------------------------------------------------------

def test_cleanup_old_data_is_celery_task(set_test_env_vars):
    """INC-04: cleanup_old_data es un Celery task registrado."""
    from app.tasks.maintenance import cleanup_old_data

    # Verificar que es una tarea Celery (tiene .delay, .apply_async)
    assert hasattr(cleanup_old_data, "delay")
    assert hasattr(cleanup_old_data, "apply_async")


def test_cleanup_old_data_task_name(set_test_env_vars):
    """INC-04: cleanup_old_data tiene name='tasks.cleanup_old_data'."""
    from app.tasks.maintenance import cleanup_old_data

    assert cleanup_old_data.name == "tasks.cleanup_old_data"


def test_cleanup_old_data_returns_dict_with_counts(set_test_env_vars):
    """INC-04: cleanup_old_data retorna dict con metrics_deleted e incidents_deleted."""
    from app.tasks.maintenance import _cleanup_async

    mock_factory, mock_session = make_mock_db_session(
        metrics_rowcount=10, incidents_rowcount=4
    )

    with patch("app.tasks.maintenance.AsyncSessionLocal", mock_factory):
        result = asyncio.run(_cleanup_async())

    assert isinstance(result, dict)
    assert "metrics_deleted" in result
    assert "incidents_deleted" in result
    assert result["metrics_deleted"] == 10
    assert result["incidents_deleted"] == 4


def test_cleanup_old_data_deletes_metrics_with_correct_sql(set_test_env_vars):
    """MK-03: DELETE metrics usa WHERE recorded_at < NOW() - INTERVAL '30 days'."""
    from app.tasks.maintenance import _cleanup_async

    mock_factory, mock_session = make_mock_db_session()

    with patch("app.tasks.maintenance.AsyncSessionLocal", mock_factory):
        asyncio.run(_cleanup_async())

    # Primera llamada a execute: DELETE metrics
    first_call = mock_session.execute.call_args_list[0]
    sql_text = str(first_call[0][0])
    assert "metrics" in sql_text
    assert "recorded_at" in sql_text
    assert "30 days" in sql_text


def test_cleanup_old_data_deletes_incidents_with_resolved_at_not_null(set_test_env_vars):
    """
    INC-04: DELETE incidents usa WHERE resolved_at IS NOT NULL.
    CRITICO: incidentes abiertos (NULL) nunca se borran.
    """
    from app.tasks.maintenance import _cleanup_async

    mock_factory, mock_session = make_mock_db_session()

    with patch("app.tasks.maintenance.AsyncSessionLocal", mock_factory):
        asyncio.run(_cleanup_async())

    # Segunda llamada a execute: DELETE incidents
    second_call = mock_session.execute.call_args_list[1]
    sql_text = str(second_call[0][0])
    assert "incidents" in sql_text
    assert "resolved_at IS NOT NULL" in sql_text
    assert "30 days" in sql_text


def test_cleanup_old_data_source_has_not_null_guard(set_test_env_vars):
    """
    T-3-17: El codigo fuente contiene 'resolved_at IS NOT NULL' explicitamente
    como guarda critica contra borrar incidentes abiertos.
    """
    from app.tasks.maintenance import _cleanup_async

    source = inspect.getsource(_cleanup_async)
    assert "resolved_at IS NOT NULL" in source


def test_cleanup_old_data_commits_transaction(set_test_env_vars):
    """INC-04: cleanup_old_data hace commit despues de los DELETE."""
    from app.tasks.maintenance import _cleanup_async

    mock_factory, mock_session = make_mock_db_session()

    with patch("app.tasks.maintenance.AsyncSessionLocal", mock_factory):
        asyncio.run(_cleanup_async())

    mock_session.commit.assert_called_once()


def test_cleanup_old_data_executes_two_deletes(set_test_env_vars):
    """INC-04/MK-03: cleanup ejecuta exactamente 2 sentencias DELETE (metrics + incidents)."""
    from app.tasks.maintenance import _cleanup_async

    mock_factory, mock_session = make_mock_db_session()

    with patch("app.tasks.maintenance.AsyncSessionLocal", mock_factory):
        asyncio.run(_cleanup_async())

    assert mock_session.execute.call_count == 2


def test_cleanup_old_data_zero_deleted_when_nothing_old(set_test_env_vars):
    """INC-04: retorna 0/0 cuando no hay datos con mas de 30 dias."""
    from app.tasks.maintenance import _cleanup_async

    mock_factory, mock_session = make_mock_db_session(
        metrics_rowcount=0, incidents_rowcount=0
    )

    with patch("app.tasks.maintenance.AsyncSessionLocal", mock_factory):
        result = asyncio.run(_cleanup_async())

    assert result["metrics_deleted"] == 0
    assert result["incidents_deleted"] == 0


# ---------------------------------------------------------------------------
# Tests del beat_schedule en celery_app.py
# ---------------------------------------------------------------------------

def test_celery_beat_schedule_has_cleanup_entry(set_test_env_vars):
    """INC-04: celery_app.conf.beat_schedule tiene entrada 'cleanup-old-data'."""
    from app.celery_app import celery_app

    beat_schedule = celery_app.conf.beat_schedule
    assert "cleanup-old-data" in beat_schedule


def test_celery_beat_cleanup_task_name(set_test_env_vars):
    """INC-04: la entrada cleanup-old-data apunta a 'tasks.cleanup_old_data'."""
    from app.celery_app import celery_app

    entry = celery_app.conf.beat_schedule["cleanup-old-data"]
    assert entry["task"] == "tasks.cleanup_old_data"


def test_celery_beat_cleanup_uses_crontab_hour_3(set_test_env_vars):
    """INC-04: cleanup-old-data usa crontab con hour=3, minute=0 (3am diario)."""
    from app.celery_app import celery_app
    from celery.schedules import crontab

    entry = celery_app.conf.beat_schedule["cleanup-old-data"]
    schedule = entry["schedule"]
    assert isinstance(schedule, crontab)
    # Verificar que es 3am (hour=3, minute=0)
    assert schedule.hour == {3}
    assert schedule.minute == {0}


def test_celery_app_includes_maintenance_module(set_test_env_vars):
    """INC-04: celery_app incluye 'app.tasks.maintenance' en include list."""
    from app.celery_app import celery_app

    includes = list(celery_app.conf.include)
    assert "app.tasks.maintenance" in includes
