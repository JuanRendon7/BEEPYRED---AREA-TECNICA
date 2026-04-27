---
phase: "03-mikrotik-alertas-incidentes"
plan: "02"
subsystem: "alerts-incidents"
tags: [telegram, celery, incidents, alerts, debounce, select-for-update]
dependency_graph:
  requires:
    - "02-foundation: AsyncSessionLocal, Device model, polling.py _ping_and_update"
    - "03-01: ALERT_DEBOUNCE_SECONDS en config.py (detectado ausente, agregado como deviation)"
  provides:
    - "send_telegram_alert() — outbound Telegram via async with Bot(token)"
    - "handle_device_down / handle_device_recovery — Celery tasks con atomicidad SELECT FOR UPDATE"
    - "open_incident_if_not_exists / close_incident — helpers de incidente para Plan 03-03"
  affects:
    - "backend/app/tasks/polling.py — dispara alert tasks en transiciones de estado"
    - "backend/app/celery_app.py — include actualizado"
tech_stack:
  added:
    - "python-telegram-bot==21.x: async with Bot(token) outbound-only"
  patterns:
    - "Deferred import dentro de funcion para evitar circular import (polling -> alerts)"
    - "SELECT FOR UPDATE via .with_for_update() para atomicidad de incidentes"
    - "_get_bot_class() seam para mockear Bot en tests sin instalar telegram en CI"
    - "asyncio.run() en Celery task sincronico (mismo patron de polling.py)"
key_files:
  created:
    - "backend/app/services/telegram.py"
    - "backend/app/tasks/alerts.py"
    - "backend/tests/unit/test_telegram.py"
    - "backend/tests/unit/test_alerts.py"
  modified:
    - "backend/app/tasks/polling.py"
    - "backend/app/celery_app.py"
    - "backend/app/core/config.py"
    - "backend/tests/unit/test_polling.py"
decisions:
  - "[03-02] _get_bot_class() seam en telegram.py permite mockear Bot sin instalar python-telegram-bot en CI — evita ModuleNotFoundError en entorno de test local"
  - "[03-02] Deferred import de alerts dentro de _ping_and_update() — import a nivel de modulo causaria circular import (polling importa alerts, alerts importa modelos que ya importa polling)"
  - "[03-02] close_incident() no hace commit — el caller lo hace junto a recovery_alert_sent=True para que ambos queden en la misma transaccion atomica"
metrics:
  duration: "~35m"
  completed_date: "2026-04-26"
  tasks_completed: 3
  files_modified: 8
  tests_added: 25
  tests_total: 112
requirements:
  - ALERT-01
  - ALERT-02
  - ALERT-03
  - ALERT-04
  - ALERT-05
  - INC-01
  - INC-02
---

# Phase 03 Plan 02: Alert Engine + Telegram + Incident Lifecycle Summary

Pipeline completo de alertas Telegram outbound-only + ciclo de vida de incidentes con atomicidad SELECT FOR UPDATE y debounce anti-flapping.

## What Was Built

### backend/app/services/telegram.py
Wrapper async para Telegram Bot outbound-only usando `async with Bot(token) as bot:`.

- `format_down_message(device_name, ip, site, timestamp)` — HTML con nombre, IP en `<code>`, sitio, timestamp UTC
- `format_up_message(device_name, ip, site, duration_seconds)` — HTML con duracion formateada (Xh Xm Xs / Xm Xs)
- `send_telegram_alert(text)` — guard si token/chat_id vacios (retorna sin error), usa `_get_bot_class()` seam para testabilidad
- `_get_bot_class()` — seam de inyeccion que permite mockear `telegram.Bot` en tests sin que la libreria este instalada en el entorno de test

### backend/app/tasks/alerts.py
Tasks Celery para el pipeline de alertas con ciclo de vida de incidentes atomico.

- `handle_device_down(device_id)` — Celery task sincronico, llama `_handle_device_down_async()`
- `handle_device_recovery(device_id)` — Celery task sincronico, llama `_handle_device_recovery_async()`
- `open_incident_if_not_exists(db, device_id)` — SELECT FOR UPDATE, INSERT si no existe (INC-01)
- `close_incident(db, device_id)` — SELECT FOR UPDATE, calcula duration_seconds (INC-02)

Flujo handle_device_down:
1. Valida que device existe (T-3-11)
2. Abre incidente atomicamente (SELECT FOR UPDATE)
3. Verifica si incidente ya cerrado (ALERT-04 debounce)
4. Envia Telegram DOWN con format_down_message()
5. Marca alert_sent=True y hace commit (ALERT-05)

Flujo handle_device_recovery:
1. Valida que device existe
2. Cierra incidente con duration_seconds calculado (INC-02)
3. Envia Telegram UP con format_up_message() y duracion
4. Marca recovery_alert_sent=True y hace commit (ALERT-05)

### Modificaciones a backend/app/tasks/polling.py
Enganche de alert tasks en `_ping_and_update()` al detectar transicion de estado:

```python
if new_status == DeviceStatus.DOWN:
    handle_device_down.apply_async(
        args=[device.id],
        countdown=settings.ALERT_DEBOUNCE_SECONDS,
    )
elif new_status == DeviceStatus.UP and previous_status == DeviceStatus.DOWN:
    handle_device_recovery.delay(device.id)
```

Import diferido dentro de la funcion (no a nivel de modulo) para evitar circular import.

### Modificaciones a backend/app/celery_app.py
`app.tasks.alerts` agregado al `include` list para autodescubrimiento de Celery.

## Interfaces Exported

```python
# backend/app/services/telegram.py
def format_down_message(device_name: str, ip: str, site: str | None, timestamp: datetime) -> str
def format_up_message(device_name: str, ip: str, site: str | None, duration_seconds: int) -> str
async def send_telegram_alert(text: str) -> None

# backend/app/tasks/alerts.py
@shared_task(name="tasks.handle_device_down")
def handle_device_down(device_id: int) -> dict

@shared_task(name="tasks.handle_device_recovery")
def handle_device_recovery(device_id: int) -> dict

async def open_incident_if_not_exists(db: AsyncSession, device_id: int) -> Incident
async def close_incident(db: AsyncSession, device_id: int) -> Incident | None
```

## Test Results

| Archivo | Tests | Estado |
|---------|-------|--------|
| test_telegram.py | 11 | PASS |
| test_alerts.py | 14 | PASS |
| test_polling.py | 11 | PASS (2 tests actualizados con mocks de alert tasks) |
| Suite completa tests/unit/ | 112 | PASS — 0 regresiones |

Cobertura de requisitos:
- ALERT-02: format_down_message incluye nombre, IP en code, sitio, timestamp UTC
- ALERT-03: format_up_message formatea 3661s -> "1h 1m 1s", 90s -> "1m 30s"
- ALERT-04: debounce — handle_device_down suprime si incidente ya cerrado
- ALERT-05: alert_sent y recovery_alert_sent marcados post-envio
- INC-01: open_incident_if_not_exists usa with_for_update()
- INC-02: close_incident calcula duration_seconds correctamente
- T-3-11: device_id validado via SELECT antes de ejecutar logica de alertas

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] ALERT_DEBOUNCE_SECONDS faltaba en config.py**
- **Found during:** Inicio del plan, lectura de read_first files
- **Issue:** El plan 03-02 referencia `settings.ALERT_DEBOUNCE_SECONDS` pero el setting nunca fue agregado a `backend/app/core/config.py` en Plan 03-01
- **Fix:** Agregado `ALERT_DEBOUNCE_SECONDS: int = 120` con comentario explicativo al bloque de umbrales de alerta
- **Files modified:** `backend/app/core/config.py`
- **Commit:** d143129

**2. [Rule 1 - Bug] Tests de polling fallaban al enquetar Celery tasks reales**
- **Found during:** Tarea 3 — run completo de tests/unit/
- **Issue:** `test_consecutive_failures_down_at_threshold` y `test_consecutive_failures_reset_on_success` activan transiciones UP->DOWN y DOWN->UP. Con el nuevo codigo, esas transiciones ejecutan el import diferido de alerts y luego llaman `.apply_async()` / `.delay()` intentando conectar a Redis/AMQP real
- **Fix:** Agregado mock de `handle_device_down` y `handle_device_recovery` en cada test usando `patch("app.tasks.alerts.handle_device_down", ...)` y `patch("app.tasks.alerts.handle_device_recovery", ...)`
- **Files modified:** `backend/tests/unit/test_polling.py`
- **Commit:** baca7e0

## Known Stubs

- `send_telegram_alert()` no se prueba contra la API real de Telegram — usa mock de `_get_bot_class()`. Esto es intencional: los tests unitarios no deben depender de conexion externa. La validacion contra Telegram real se hara en Phase 6 (verificacion end-to-end en produccion).

## Threat Flags

Estado de amenazas T-3-07 a T-3-12 definidas en el plan:

| Threat ID | Estado | Notas |
|-----------|--------|-------|
| T-3-07 | Mitigado | `TELEGRAM_BOT_TOKEN` es `str` (aceptado de Phase 1). Guard retorna sin error si vacio. Token NUNCA se loggea en `send_telegram_alert()`. |
| T-3-08 | Aceptado | IP en mensaje Telegram — canal privado del tecnico, aceptable para v1 |
| T-3-09 | Mitigado | `with_for_update()` en `open_incident_if_not_exists()` (linea 186) y `close_incident()` (linea 223) |
| T-3-10 | Aceptado | Para v1 con pocos Mikrotik, riesgo bajo. Tasks Celery procesados secuencialmente en cola. |
| T-3-11 | Mitigado | `SELECT Device WHERE id=device_id` antes de cualquier logica en `_handle_device_down_async` y `_handle_device_recovery_async` |
| T-3-12 | Aceptado | Datos de DB interna insertados por tecnico autenticado. `html.escape()` se aplica en v2 si hay input externo. |

## Self-Check: PASSED

| Check | Result |
|-------|--------|
| backend/app/services/telegram.py | FOUND |
| backend/app/tasks/alerts.py | FOUND |
| backend/tests/unit/test_telegram.py | FOUND |
| backend/tests/unit/test_alerts.py | FOUND |
| commit d143129 (Task 1) | FOUND |
| commit 334c5a7 (Task 2) | FOUND |
| commit baca7e0 (Task 3) | FOUND |
| 112 tests passing | PASS |
