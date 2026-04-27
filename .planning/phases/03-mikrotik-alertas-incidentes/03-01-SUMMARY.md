---
phase: 03-mikrotik-alertas-incidentes
plan: "01"
subsystem: mikrotik-collector
tags:
  - mikrotik
  - routeros-api
  - circuit-breaker
  - thresholds
  - celery
  - redis
dependency_graph:
  requires:
    - 02-foundation (AsyncSessionLocal, Device model, DeviceCredential model, Metric model, Alert model)
    - 01-infrastructure (Redis, PostgreSQL, Celery worker)
  provides:
    - circuit_breaker.py (is_circuit_open, record_api_failure, record_api_success)
    - thresholds.py (get_threshold)
    - mikrotik.py (poll_mikrotik_device, poll_all_mikrotik)
  affects:
    - celery_app.py (include list + beat_schedule)
    - backend/requirements.txt (librouteros, python-telegram-bot)
tech_stack:
  added:
    - librouteros==4.0.1 (RouterOS API protocol — port 8728/8729)
    - python-telegram-bot==21.* (async Telegram Bot API — usado en Plan 02)
  patterns:
    - circuit breaker Redis TTL (cb:open:{id}, cb:fails:{id})
    - get() defensivo en parsing RouterOS API (sin KeyError)
    - asyncio.run() en Celery task (patron establecido en Phase 2)
    - insert(Metric) con lista de dicts — una transaccion por ciclo
key_files:
  created:
    - backend/app/services/__init__.py
    - backend/app/services/circuit_breaker.py
    - backend/app/services/thresholds.py
    - backend/app/tasks/mikrotik.py
    - backend/tests/unit/test_circuit_breaker.py
    - backend/tests/unit/test_thresholds.py
    - backend/tests/unit/test_mikrotik.py
  modified:
    - backend/app/core/config.py (MIKROTIK_API_PORT=8728)
    - backend/app/celery_app.py (app.tasks.mikrotik en include + poll-mikrotik-devices en beat_schedule)
    - backend/requirements.txt (librouteros==4.0.1, python-telegram-bot==21.*)
decisions:
  - "[Phase 03-01]: ALERT_DEBOUNCE_SECONDS ya estaba en config.py desde un commit previo — no se duplico"
  - "[Phase 03-01]: app.tasks.alerts ya estaba en celery_app include desde commit 03-02 (planes ejecutados fuera de orden) — solo se agrego app.tasks.mikrotik"
  - "[Phase 03-01]: api.close() sincronica en bloque finally — librouteros no requiere await para close()"
  - "[Phase 03-01]: record_api_failure() elimina cb:fails:{id} al abrir el circuit — evita conteo doble si la clave no expiro"
metrics:
  duration: "~20 minutos"
  completed_at: "2026-04-27T03:44:00Z"
  tasks_completed: 3
  tests_added: 36
  files_created: 7
  files_modified: 3
---

# Phase 03 Plan 01: Mikrotik Collector + Circuit Breaker + Thresholds Summary

**One-liner:** Collector RouterOS API con circuit breaker Redis TTL-5min y servicio de umbrales DB>env configurables para Celery beat polling.

## What Was Built

### circuit_breaker.py
Servicio sin estado que implementa el patrón circuit breaker usando claves Redis con TTL:
- `is_circuit_open(redis, device_id)` — consulta `cb:open:{id}` antes de conectar
- `record_api_failure(redis, device_id)` — incrementa `cb:fails:{id}` con TTL; al llegar a 3 abre el circuit con `setex cb:open:{id} 300 "1"` y elimina el contador
- `record_api_success(redis, device_id)` — elimina ambas claves, reseteando el estado

### thresholds.py
Servicio de umbrales con lookup en cascada: DB device-especifico → DB global → env var fallback:
- `get_threshold(db, alert_type, device_id=None)` — una función con tres niveles de precedencia
- Fallback mapeado para `cpu_high` → `settings.CPU_ALERT_THRESHOLD_PCT` y `signal_low` → `settings.ONU_SIGNAL_MIN_DBM`
- Tipos no conocidos retornan `None` sin excepción

### mikrotik.py
Task Celery + collector async completo:
- `poll_mikrotik_device(device_id)` — task Celery individual por dispositivo
- `poll_all_mikrotik()` — orquestador que encola tasks para todos los Mikrotik activos
- `_collect_mikrotik_async()` — flujo completo: check circuit → obtener credencial → conectar → recolectar → escribir metrics → record_api_success
- `_fetch_routeros_data()` — apertura RouterOS API, lectura de `/system/resource` y `/interface`, cierre garantizado en `finally`
- `_parse_metrics()` — función pura, convierte dict RouterOS → lista de dicts para insert(Metric); `.get()` defensivo en todos los campos
- `_write_metrics()` — insert(Metric) con lista en una sola transacción, no-op si lista vacía

## Interfaces Exported

```python
# backend/app/services/circuit_breaker.py
async def is_circuit_open(redis_client: aioredis.Redis, device_id: int) -> bool
async def record_api_failure(redis_client: aioredis.Redis, device_id: int) -> bool  # True si acaba de abrirse
async def record_api_success(redis_client: aioredis.Redis, device_id: int) -> None

CIRCUIT_OPEN_TTL: int = 300   # 5 minutos
CIRCUIT_FAIL_THRESHOLD: int = 3

# backend/app/services/thresholds.py
async def get_threshold(db: AsyncSession, alert_type: str, device_id: int | None = None) -> float | None

# backend/app/tasks/mikrotik.py
@shared_task(name="tasks.poll_mikrotik_device")
def poll_mikrotik_device(device_id: int) -> dict

@shared_task(name="tasks.poll_all_mikrotik")
def poll_all_mikrotik() -> dict

# Funciones internas testables
async def _collect_mikrotik_async(device_id: int) -> dict
async def _fetch_routeros_data(ip, username, password, device_id, redis_client) -> dict | None
def _parse_metrics(raw: dict) -> list[dict]
async def _write_metrics(device_id: int, metrics: list[dict]) -> None
```

## Test Results

| Archivo | Tests | Requerimientos |
|---------|-------|----------------|
| test_circuit_breaker.py | 10 pasan | MK-04 |
| test_thresholds.py | 8 pasan | ALERT-06 |
| test_mikrotik.py | 18 pasan | MK-01, MK-02, MK-03, MK-04 |
| **Suite completa tests/unit/** | **112 pasan** | Sin regresiones |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Config ya existente] ALERT_DEBOUNCE_SECONDS ya estaba en config.py**
- **Found during:** Task 1 al leer config.py
- **Issue:** El plan indicaba agregar `ALERT_DEBOUNCE_SECONDS` pero ya existía desde un commit anterior (Plan 03-02 que fue ejecutado antes que 03-01 en el historial git)
- **Fix:** Solo se agregó `MIKROTIK_API_PORT` — no se duplicó la variable existente
- **Files modified:** backend/app/core/config.py
- **Commit:** 23582ea

**2. [Rule 2 - celery_app ya modificado] app.tasks.alerts ya en include list**
- **Found during:** Task 3 al leer celery_app.py
- **Issue:** El commit `baca7e0` (plan 03-02) ya había agregado `app.tasks.alerts` al include — solo faltaba `app.tasks.mikrotik` y la entrada beat
- **Fix:** Se agregaron solo los elementos faltantes
- **Files modified:** backend/app/celery_app.py
- **Commit:** incluido en baca7e0 (git stash/pop durante ejecución)

## Known Stubs

Ninguno. El collector es funcional end-to-end con librouteros real:
- `tx-bits-per-second` y `rx-bits-per-second` son campos estándar de RouterOS `/interface` disponibles en RouterOS 6.x y 7.x
- Si un campo no está disponible en hardware específico, `.get()` defensivo omite la métrica silenciosamente (comportamiento correcto, no stub)

## Threat Flags

Todos los threats del plan fueron implementados/revisados:

| Threat ID | Estado | Notas |
|-----------|--------|-------|
| T-3-01 | Mitigado | Solo se loggea device_id y tipo de error — nunca username/password en logs |
| T-3-02 | Mitigado | `.get()` defensivo + cast explícito `float()` en `_parse_metrics()` |
| T-3-03 | Aceptado | Max 1000 keys Redis con TTL 5min para 500 dispositivos — negligible |
| T-3-04 | Aceptado | `MIKROTIK_API_PORT` validado por Pydantic como `int` |
| T-3-05 | Aceptado | Redis en red privada Railway — claves no contienen datos sensibles |
| T-3-06 | Aceptado | Puerto 8728 sin TLS aceptado para v1 red privada ISP — migración a 8729 en v2 |

## Self-Check: PASSED

| Check | Result |
|-------|--------|
| backend/app/services/circuit_breaker.py | FOUND |
| backend/app/services/thresholds.py | FOUND |
| backend/app/tasks/mikrotik.py | FOUND |
| backend/tests/unit/test_circuit_breaker.py | FOUND |
| backend/tests/unit/test_thresholds.py | FOUND |
| backend/tests/unit/test_mikrotik.py | FOUND |
| Commit 23582ea (circuit_breaker + thresholds) | FOUND |
| Commit e96ef2e (mikrotik collector) | FOUND |
| 112 tests pasan (suite completa) | PASSED |
