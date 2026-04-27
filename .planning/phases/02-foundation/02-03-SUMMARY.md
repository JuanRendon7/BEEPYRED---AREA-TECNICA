---
phase: 02-foundation
plan: "03"
subsystem: polling-worker
tags: [celery, asyncio, icmp, redis, pubsub, debounce]
dependency_graph:
  requires: [02-01, 02-02]
  provides: [icmp-polling, device-status-events]
  affects: [02-04-sse-endpoint]
tech_stack:
  added: [celery==5.6.3, redis==6.4.0]
  patterns: [asyncio.Semaphore, asyncio.run-in-celery-task, consecutive-failures-debounce, redis-pubsub]
key_files:
  created:
    - backend/app/tasks/polling.py
    - backend/tests/unit/test_polling.py
  modified:
    - backend/app/celery_app.py
key_decisions:
  - "asyncio.run() en task Celery sincronico — no loop.run_until_complete (deprecated Python 3.10+)"
  - "subprocess ping -c 1 -W {timeout} — iputils-ping usa ICMP datagram socket (sin NET_RAW), funciona en Railway"
  - "consecutive_failures en columna DB (no Redis) — persiste reinicios del worker, auditoria disponible"
  - "publish_status_update solo en cambio de estado (no en cada poll) — reduce trafico Redis"
  - "expires=POLL_INTERVAL_SECONDS-5 en beat_schedule — previene acumulacion de tareas si worker lento (T-2-21)"
  - "redis 6.4.0 instalado (no 7.4.0 del requirements.txt) — conflicto de dependencias con kombu; compatible con redis.asyncio API"
metrics:
  duration: "2m 42s"
  completed: "2026-04-27"
  tasks_completed: 2
  files_changed: 3
  tests_added: 11
  tests_total: 51
---

# Phase 02 Plan 03: ICMP Polling Worker Summary

**One-liner:** Worker Celery con ping_host subprocess + asyncio.Semaphore(50) + consecutive_failures debounce de 3 fallos + publicacion Redis pub/sub canal device_status.

## What Was Built

### `backend/app/tasks/polling.py`

Nucleo operacional del NOC. Tres funciones publicas:

**`ping_host(ip, timeout)`**
- Usa `asyncio.create_subprocess_exec("ping", "-c", "1", "-W", timeout, ip)` — iputils-ping moderno, no requiere NET_RAW
- `asyncio.Semaphore(MAX_CONCURRENT_CONNECTIONS=50)` limita concurrencia global por proceso (POLL-02)
- `asyncio.wait_for(proc.wait(), timeout=timeout+1)` aísla fallos individuales — un host colgado no bloquea el ciclo (POLL-05)
- En `TimeoutError` o `OSError`: llama `proc.kill()` y retorna False

**`publish_status_update(device_id, new_status)`**
- Crea conexion Redis efimera via `redis.asyncio.from_url(settings.REDIS_URL)`
- Publica `{"id": device_id, "status": new_status}` al canal `"device_status"` (POLL-04)
- Cierra conexion con `aclose()` en bloque finally — sin leaks

**`_ping_and_update(device)`** — funcion interna
- Lógica de debounce POLL-03:
  - Exito: `consecutive_failures = 0`, `status = UP`, `last_seen_at = now()`
  - Fallo: `consecutive_failures += 1`; si `>= CONSECUTIVE_FAILURES_THRESHOLD (3)`: `status = DOWN`
  - Publica a Redis SOLO cuando el status cambia

**`poll_all_devices()`** — Celery task `@shared_task(name="tasks.poll_all_devices")`
- Task sincronico — usa `asyncio.run(_poll_all_devices_async())` (no deprecated `loop.run_until_complete`)
- Retorna `{polled, up, down, errors}` para logging de Celery
- `asyncio.gather(..., return_exceptions=True)` — un fallo no cancela los otros pings

### `backend/app/celery_app.py`

Beat schedule configurado:
```python
beat_schedule={
    "poll-all-devices": {
        "task": "tasks.poll_all_devices",
        "schedule": settings.POLL_INTERVAL_SECONDS,  # 60s
        "options": {"expires": settings.POLL_INTERVAL_SECONDS - 5},  # anti-acumulacion
    },
}
```
- `include` actualizado a `["app.tasks.polling"]` — `app.tasks.maintenance` removido (no existe aún)

### `backend/tests/unit/test_polling.py`

11 tests, todos pasando:

| Test | Requisito |
|------|-----------|
| test_ping_host_returns_true_on_returncode_0 | POLL-05 |
| test_ping_host_returns_false_on_returncode_1 | POLL-05 |
| test_ping_host_returns_false_on_timeout | POLL-05 |
| test_ping_host_kills_process_on_timeout | POLL-05 |
| test_semaphore_max_concurrent_connections | POLL-02 |
| test_consecutive_failures_increments_on_failure | POLL-03 |
| test_consecutive_failures_down_at_threshold | POLL-03 |
| test_consecutive_failures_reset_on_success | POLL-03 |
| test_publish_status_update_publishes_correct_payload | POLL-04 |
| test_publish_status_update_closes_redis_connection | POLL-04 |
| test_beat_schedule_has_poll_all_devices | POLL-01 |

## Test Results

```
tests/unit/test_polling.py — 11 passed
tests/unit/ (suite completa) — 51 passed, 0 failed
```

## Commits

| Hash | Mensaje |
|------|---------|
| 7539c50 | feat(02-03): implement ICMP polling worker with consecutive_failures debounce |
| 8075839 | feat(02-03): add poll-all-devices beat schedule to celery_app |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Celery y redis no estaban instalados en el entorno de desarrollo**
- **Found during:** Fase RED del TDD — tests fallaban con `ModuleNotFoundError: No module named 'celery'`
- **Issue:** celery[redis]==5.6.3 y redis==7.4.0 estaban en requirements.txt pero no instalados en el venv local
- **Fix:** `pip install "celery[redis]" redis` — instaló celery==5.6.3 y redis==6.4.0 (kombu 5.6.x requiere redis <7.x en la resolución de dependencias)
- **Impact:** redis 6.4.0 en lugar de 7.4.0; la API `redis.asyncio` es compatible — ningún cambio en código
- **Files modified:** Solo entorno local (pip) — requirements.txt ya tenía las entradas correctas

**2. [Rule 1 - Clarification] `grep "loop.run_until_complete"` detecta línea en docstring**
- El criterio de aceptación `grep "loop.run_until_complete" ... NO retorna match` técnicamente falla porque la línea 17 del docstring menciona el patrón en un comentario de advertencia
- El código ejecutable NO usa `loop.run_until_complete` — solo `asyncio.run()` en línea 47
- Esta es documentación intencional del por qué NO se usa el patrón deprecated

## Known Stubs

Ninguno — la implementación está completa. `poll_all_devices` conecta a DB real, ejecuta pings reales, y publica a Redis real. Los tests usan mocks pero el código de producción no tiene stubs.

## Threat Flags

Ninguna nueva superficie de red o autenticación más allá de lo documentado en el threat model del plan (T-2-20 a T-2-26).

## Self-Check: PASSED
