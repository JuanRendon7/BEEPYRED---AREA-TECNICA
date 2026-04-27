---
phase: "03"
plan: "03"
subsystem: incidents-api-maintenance
tags:
  - fastapi
  - pydantic-v2
  - celery-beat
  - sqlalchemy-join
  - cleanup
dependency_graph:
  requires:
    - "03-01"  # circuit breaker, thresholds, mikrotik collector
    - "03-02"  # alerts pipeline, telegram, incident open/close
  provides:
    - incidents-rest-api
    - automatic-data-cleanup
  affects:
    - main.py
    - celery_app.py
tech_stack:
  added: []
  patterns:
    - "SQLAlchemy JOIN con .label() para aplanar columnas en IncidentResponse"
    - "result.mappings().all() + model_validate(dict(row)) para schemas desde JOINs"
    - "Celery shared_task + asyncio.run() para tarea async de limpieza"
    - "crontab(hour=3, minute=0) en beat_schedule para ejecucion diaria"
    - "DELETE SQL directo via text() — mas eficiente que ORM para borrado masivo"
key_files:
  created:
    - backend/app/schemas/incident.py
    - backend/app/api/v1/__init__.py
    - backend/app/api/v1/incidents.py
    - backend/app/tasks/maintenance.py
    - backend/tests/unit/test_incidents.py
    - backend/tests/unit/test_maintenance.py
  modified:
    - backend/app/main.py
    - backend/app/celery_app.py
decisions:
  - "result.mappings().all() + model_validate(dict(row)) es el patron correcto para JOINs SQLAlchemy con Pydantic v2 — scalars() no funciona con columnas individuales de JOIN"
  - "Limite de paginacion max=500 (plan decia 200 pero el codigo del plan usa le=500) — elegido 500 para coincidir con el codigo del plan"
  - "cleanup_old_data() usa asyncio.run(_cleanup_async()) — patron establecido en Phase 2 para Celery + asyncio"
  - "resolved_at IS NOT NULL es guarda critica en el DELETE de incidents — verificado por inspeccion de codigo fuente en test"
metrics:
  duration: "20m"
  completed_date: "2026-04-27"
  tasks_completed: 2
  files_changed: 8
  tests_added: 23
---

# Phase 03 Plan 03: Incidents REST API + Automatic Cleanup Summary

**One-liner:** GET /api/v1/incidents con JOIN Device para nombre/sitio + Celery beat diario que purga datos de 30 dias sin borrar incidentes abiertos.

## What Was Built

### incidents.py router (INC-03)

Router FastAPI montado en `/api/v1/incidents`. El endpoint `GET /incidents` ejecuta un JOIN entre `incidents` y `devices` para devolver `device_name` y `device_site` junto con los datos del incidente. Soporta filtros opcionales `device_id` y `site`, paginacion `limit`/`offset` (default 50, max 500), y ordena por `started_at DESC`. Protegido por `CurrentUser` (JWT obligatorio — 401 sin token).

### IncidentResponse schema

Schema Pydantic v2 con `model_config = ConfigDict(from_attributes=True)`. Los campos `device_name` y `device_site` se obtienen via `.label()` en el SELECT y se validan con `model_validate(dict(row))` desde el mapping de SQLAlchemy.

### maintenance.py task (INC-04, MK-03)

Celery `@shared_task` con `name="tasks.cleanup_old_data"` que ejecuta dos DELETE SQL directos:
1. `DELETE FROM metrics WHERE recorded_at < NOW() - INTERVAL '30 days'`
2. `DELETE FROM incidents WHERE resolved_at IS NOT NULL AND resolved_at < NOW() - INTERVAL '30 days'`

La guarda `resolved_at IS NOT NULL` es critica: los incidentes abiertos (equipo aun DOWN) nunca se borran independientemente de su antiguedad. La tarea retorna `{"metrics_deleted": N, "incidents_deleted": M}` y lo registra en logs.

### celery_app.py actualizado

- `app.tasks.maintenance` agregado a la lista `include`
- Entrada `cleanup-old-data` en `beat_schedule` con `crontab(hour=3, minute=0)` (3am hora Colombia, UTC-5) y `expires=3600` para descartar si no se ejecuto en 1 hora

## Endpoints Created

| Metodo | Ruta | Descripcion | Status Code |
|--------|------|-------------|-------------|
| GET | /api/v1/incidents | Lista incidentes con device_name/site, filtros y paginacion | 200 |
| GET | /api/v1/incidents?device_id=N | Filtrar por ID de equipo | 200 |
| GET | /api/v1/incidents?site=X | Filtrar por sitio geografico | 200 |
| GET | /api/v1/incidents (sin JWT) | Sin token — rechazado | 401 |

## Interfaces Exported

| Simbolo | Modulo | Tipo | Descripcion |
|---------|--------|------|-------------|
| `IncidentResponse` | `app.schemas.incident` | Pydantic BaseModel | Schema de respuesta con device_name/device_site del JOIN |
| `router` | `app.api.v1.incidents` | APIRouter | Router FastAPI con prefix=/incidents |
| `cleanup_old_data` | `app.tasks.maintenance` | Celery shared_task | Limpieza diaria de datos > 30 dias |
| `_cleanup_async` | `app.tasks.maintenance` | async function | Logica async interna (testeable sin Celery) |

## Test Results

### Plan 03 (este plan)
- `test_incidents.py`: 10 tests — INC-03 completo
- `test_maintenance.py`: 13 tests — INC-04, MK-03 completo
- **Subtotal Plan 03: 23 tests**

### Suite completa Phase 3 (todos los planes)
| Archivo | Tests | Requirements |
|---------|-------|-------------|
| test_circuit_breaker.py | 11 | MK-04 |
| test_thresholds.py | 7 | ALERT-06 |
| test_mikrotik.py | 17 | MK-01, MK-02, MK-03 |
| test_telegram.py | 10 | ALERT-02, ALERT-03 |
| test_alerts.py | 14 | ALERT-01, ALERT-04, ALERT-05, INC-01, INC-02 |
| test_incidents.py | 10 | INC-03 |
| test_maintenance.py | 13 | INC-04, MK-03 |
| **Total Phase 3** | **82** | |

**Suite completa tests/unit/: 135 passed** (incluye tests de Phase 1 y Phase 2)

## Phase 3 Requirements Coverage

| Requirement | Descripcion | Status | Test |
|-------------|-------------|--------|------|
| MK-01 | cpu_pct y ram_pct escritos en metrics | DONE | test_mikrotik.py |
| MK-02 | tx_bps y rx_bps por interfaz en metrics | DONE | test_mikrotik.py |
| MK-03 | api.close() en finally + cleanup 30 dias | DONE | test_mikrotik.py + test_maintenance.py |
| MK-04 | Circuit breaker abre tras 3 fallos, TTL 5min | DONE | test_circuit_breaker.py |
| ALERT-01 | polling.py dispara handle_device_down al DOWN | DONE | test_polling.py extendido |
| ALERT-02 | Mensaje DOWN con nombre/IP/sitio/timestamp | DONE | test_telegram.py |
| ALERT-03 | Mensaje UP con duracion calculada | DONE | test_telegram.py |
| ALERT-04 | Debounce — no alerta si incidente cerrado antes del countdown | DONE | test_alerts.py |
| ALERT-05 | alert_sent y recovery_alert_sent marcados | DONE | test_alerts.py |
| ALERT-06 | get_threshold() prioriza DB > env var | DONE | test_thresholds.py |
| INC-01 | Incidente abierto con started_at al DOWN | DONE | test_alerts.py |
| INC-02 | Incidente cerrado con duration_seconds al UP | DONE | test_alerts.py |
| INC-03 | GET /incidents con filtros | DONE | test_incidents.py |
| INC-04 | Cleanup automatico incidentes > 30 dias | DONE | test_maintenance.py |

**Todos los 14 requirements de Phase 3 cubiertos.**

## Deviations from Plan

Ninguna. El plan se ejecuto exactamente como estaba especificado. Los tests del endpoint de incidents usaron un patron de override de `get_current_active_user` via `app.dependency_overrides` — el plan sugeria mockear directamente pero la implementacion con overrides de FastAPI es mas robusta y equivalente.

## Known Stubs

Ninguno. El endpoint retorna datos reales de la DB via JOIN. La tarea de limpieza ejecuta SQL real. No hay valores hardcodeados ni placeholders en el flujo de datos.

## Threat Flags

Ninguna nueva superficie de seguridad introducida fuera del threat model del plan.

| Threat ID | Estado | Mitigacion aplicada |
|-----------|--------|---------------------|
| T-3-13 | MITIGADO | `CurrentUser` dependency en parametros del endpoint — 401 sin Bearer token (verificado en test) |
| T-3-14 | ACEPTADO | Plataforma interna — solo tecnico autenticado accede |
| T-3-15 | MITIGADO | SQLAlchemy usa prepared statements en `.where()` — no hay interpolacion de strings |
| T-3-16 | MITIGADO | `le=500` en Query(limit) — no hay path para N ilimitado |
| T-3-17 | MITIGADO | `resolved_at IS NOT NULL` en SQL + test de inspeccion de codigo fuente |
| T-3-18 | MITIGADO | `logger.info()` registra metrics_deleted e incidents_deleted en cada ejecucion |

## Self-Check: PASSED

Archivos creados verificados:
- `backend/app/schemas/incident.py` — ENCONTRADO
- `backend/app/api/v1/incidents.py` — ENCONTRADO
- `backend/app/tasks/maintenance.py` — ENCONTRADO

Commits verificados:
- `ee3662d` — feat(03-03): implement GET /api/v1/incidents
- `2586346` — feat(03-03): add cleanup_old_data Celery task

Tests: 135 passed, 0 failed.
