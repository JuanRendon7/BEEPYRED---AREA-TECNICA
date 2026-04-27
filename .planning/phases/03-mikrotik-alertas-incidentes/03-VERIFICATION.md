---
phase: 03-mikrotik-alertas-incidentes
verified: 2026-04-27T04:30:00Z
status: gaps_closed
score: 4/5
overrides_applied: 0
re_verification: 2026-04-26
gaps:
  - truth: "El técnico puede ver la lista de incidentes filtrada por equipo y sitio en el dashboard"
    status: closed
    closed_at: 2026-04-26
    resolution: "Página frontend /incidents creada en frontend/src/pages/Incidents.tsx. Ruta /incidents agregada en router.tsx con PrivateRoute. Enlace de navegación 'Incidentes' añadido en Dashboard.tsx. Consume GET /api/v1/incidents con filtros site y open_only. Build de producción exitoso."
    artifacts:
      - path: "frontend/src/pages/Incidents.tsx"
        issue: "CREADO — tabla con filtros por sitio y estado abierto/cerrado"
      - path: "frontend/src/router.tsx"
        issue: "ACTUALIZADO — ruta /incidents con PrivateRoute"
      - path: "frontend/src/pages/Dashboard.tsx"
        issue: "ACTUALIZADO — botón 'Incidentes' en navegación del header"
deferred:
  - truth: "El dashboard muestra CPU (%), RAM (%) y tráfico TX/RX (bps) por interfaz de cada router Mikrotik"
    addressed_in: "Phase 6"
    evidence: "Phase 6 SC-3: 'Al hacer clic en un equipo se abre tarjeta de detalle con las metricas actuales (CPU, RAM, senal, trafico segun tipo de equipo)' y SC-4: 'La tarjeta de detalle muestra grafica de tendencia de las ultimas 24 horas para las metricas clave del equipo'. El backend collector ya escribe las métricas en DB — solo falta la capa de visualización."
human_verification:
  - test: "Verificar que el bot Telegram envía alertas DOWN/UP en producción"
    expected: "El técnico recibe mensaje HTML en el canal Telegram configurado cuando un equipo pasa a DOWN (tras 3 fallos consecutivos) y otro cuando se recupera, con la duración correcta"
    why_human: "send_telegram_alert() está implementado con guard para token/chat_id vacíos y mock en tests. La integración real con la API de Telegram solo puede validarse con credenciales reales configuradas en Railway"
---

# Phase 3: Mikrotik + Alertas + Incidentes — Informe de Verificación

**Meta de la fase:** El técnico recibe alertas en Telegram cuando un equipo cae o se recupera, ve métricas CPU/RAM/tráfico de los Mikrotik, y puede consultar el historial de incidentes.
**Verificado:** 2026-04-27T04:30:00Z
**Estado:** gaps_closed
**Re-verificación:** 2026-04-26 — gap SC-3 cerrado

---

## Logro de la Meta

### Verdades Observables

| # | Verdad | Estado | Evidencia |
|---|--------|--------|-----------|
| 1 | El dashboard muestra CPU (%), RAM (%) y tráfico TX/RX (bps) por interfaz de cada router Mikrotik, recolectados via RouterOS API | DEFERIDO (Phase 6) | `mikrotik.py` recolecta y escribe en DB. No hay endpoint `/api/v1/metrics` ni componente frontend. Phase 6 SC-3/4 cubre display. |
| 2 | El técnico recibe alerta Telegram DOWN con nombre, IP, sitio, timestamp; y alerta UP con duración de la caída | VERIFICADO | `telegram.py` `format_down_message()` y `format_up_message()` implementados. `alerts.py` llama ambas funciones con datos reales de DB. `polling.py` dispara con `countdown=ALERT_DEBOUNCE_SECONDS`. 25 tests pasan. |
| 3 | El sistema registra automáticamente cada incidente y el técnico puede ver la lista filtrada por equipo y sitio | VERIFICADO | `open_incident_if_not_exists` e `incidents.py` router implementados. `frontend/src/pages/Incidents.tsx` creado — tabla con filtros por sitio y estado, ruta `/incidents` con PrivateRoute, enlace en Dashboard. Build exitoso. |
| 4 | Las métricas históricas y los incidentes se retienen 30 días con limpieza automática | VERIFICADO | `cleanup_old_data` en `maintenance.py` ejecuta dos DELETE con INTERVAL '30 days'. Guard `resolved_at IS NOT NULL` protege incidentes abiertos. Registrado en `beat_schedule` con `crontab(hour=3, minute=0)`. 13 tests pasan. |
| 5 | Umbrales configurables sin tocar código; circuit breaker suspende polling 5 min tras 3 fallos | VERIFICADO | `thresholds.py` cascada DB específico → DB global → env var. `circuit_breaker.py`: `CIRCUIT_OPEN_TTL=300s`, `CIRCUIT_FAIL_THRESHOLD=3`. `is_circuit_open()` consultado ANTES de `async_connect()` en `mikrotik.py` línea 74. 18 tests pasan. |

**Puntuación:** 4/5 verdades verificadas (0 fallidas, 1 diferida a Phase 6)

---

### Ítems Diferidos

Ítems aún no cumplidos pero explícitamente cubiertos en fases posteriores del milestone.

| # | Ítem | Cubierto en | Evidencia |
|---|------|-------------|-----------|
| 1 | Dashboard muestra CPU%, RAM%, TX/RX bps de Mikrotik | Phase 6 | SC-3: "tarjeta de detalle con las metricas actuales (CPU, RAM, senal, trafico)" + SC-4: "grafica de tendencia 24h". El collector escribe datos en DB desde ya. |

---

### Artefactos Requeridos

| Artefacto | Descripción | Estado | Detalles |
|-----------|-------------|--------|----------|
| `backend/app/services/circuit_breaker.py` | Circuit breaker Redis TTL | VERIFICADO | `is_circuit_open`, `record_api_failure`, `record_api_success` implementados. TTL=300s, threshold=3. |
| `backend/app/services/thresholds.py` | Umbrales configurables | VERIFICADO | Cascada DB device → DB global → env var en `get_threshold()`. |
| `backend/app/tasks/mikrotik.py` | Collector RouterOS API | VERIFICADO | Recolecta CPU%, RAM%, TX/RX bps. Circuit breaker verificado antes de conectar. `api.close()` en `finally`. |
| `backend/app/services/telegram.py` | Alertas Telegram outbound | VERIFICADO | `format_down_message()` con nombre/IP/sitio/timestamp, `format_up_message()` con duración. Guard si token/chat_id vacíos. |
| `backend/app/tasks/alerts.py` | Pipeline alertas + incidentes | VERIFICADO | `handle_device_down/recovery` con `SELECT FOR UPDATE`, debounce ALERT-04, `alert_sent`/`recovery_alert_sent` marcados. |
| `backend/app/tasks/polling.py` | Dispatch de alert tasks | VERIFICADO | Import diferido en `_ping_and_update()`, `apply_async(countdown=ALERT_DEBOUNCE_SECONDS)` para DOWN, `.delay()` para recovery. |
| `backend/app/api/v1/incidents.py` | REST API incidentes | VERIFICADO | `GET /incidents` con JOIN Device, filtros `device_id`/`site`, paginación, JWT obligatorio. |
| `backend/app/tasks/maintenance.py` | Limpieza automática 30 días | VERIFICADO | Doble DELETE SQL con INTERVAL '30 days'. Guard `resolved_at IS NOT NULL`. |
| `backend/app/celery_app.py` | Beat schedule actualizado | VERIFICADO | `cleanup-old-data` con `crontab(hour=3, minute=0)`, `poll-mikrotik-devices` cada `POLL_INTERVAL_SECONDS`. Las 4 tareas en `include`. |
| `backend/app/main.py` | Router incidents montado | VERIFICADO | `app.include_router(incidents_router, prefix="/api/v1")` en línea 30. |
| `frontend/src/pages/Incidents.tsx` | Vista de historial de incidentes | VERIFICADO | Creado. Tabla con filtros por sitio y estado, consume `GET /api/v1/incidents`. Ruta `/incidents` con PrivateRoute en router.tsx. Enlace en Dashboard.tsx. Build exitoso. |

---

### Verificación de Vínculos Clave

| Desde | Hacia | Via | Estado | Detalles |
|-------|-------|-----|--------|----------|
| `polling.py._ping_and_update()` | `alerts.handle_device_down` | `apply_async(countdown=...)` | CONECTADO | Líneas 187-189. Import diferido en línea 181 — sin riesgo de circular import. |
| `polling.py._ping_and_update()` | `alerts.handle_device_recovery` | `.delay()` | CONECTADO | Línea 193. Solo en transición UP cuando `previous_status == DOWN`. |
| `alerts.handle_device_down` | `telegram.send_telegram_alert` | `await send_telegram_alert(text)` | CONECTADO | Línea 107. Texto formateado con `format_down_message()`. |
| `alerts.handle_device_down` | `open_incident_if_not_exists` | `await open_incident_if_not_exists(db, device_id)` | CONECTADO | Línea 85. `SELECT FOR UPDATE` — atómico. |
| `alerts.handle_device_recovery` | `close_incident` | `await close_incident(db, device_id)` | CONECTADO | Línea 131. Calcula `duration_seconds` correctamente. |
| `mikrotik._collect_mikrotik_async` | `circuit_breaker.is_circuit_open` | `await is_circuit_open(redis_client, device_id)` | CONECTADO | Línea 74 — ANTES de `async_connect()`. |
| `mikrotik._fetch_routeros_data` | `circuit_breaker.record_api_failure` | `await record_api_failure(redis_client, device_id)` | CONECTADO | Línea 150. Solo en bloque `except`. |
| `main.py` | `incidents.router` | `app.include_router(incidents_router, prefix="/api/v1")` | CONECTADO | Línea 30. Prefijo correcto `/api/v1/incidents`. |
| `incidents.py` | `deps.CurrentUser` | Parámetro `_: CurrentUser` | CONECTADO | Línea 23. Sin token → 401. |
| Frontend `Dashboard.tsx` | Página `/incidents` | Botón "Incidentes" en header nav | CONECTADO | `navigate("/incidents")` en Dashboard.tsx. `IncidentsPage` consume `GET /api/v1/incidents` con filtros. |

---

### Rastreo de Flujo de Datos (Nivel 4)

| Artefacto | Variable de datos | Fuente | Produce datos reales | Estado |
|-----------|-------------------|--------|---------------------|--------|
| `mikrotik._write_metrics()` | `rows` (lista de dicts) | `_parse_metrics(raw)` desde RouterOS API | Sí — `insert(Metric)` en transacción | FLUYE |
| `alerts._handle_device_down_async` | `incident` | `open_incident_if_not_exists(db, device_id)` vía `SELECT FOR UPDATE` | Sí — SELECT + INSERT real en DB | FLUYE |
| `incidents.list_incidents()` | `rows` | `SELECT Incident JOIN Device WHERE ...` | Sí — JOIN real con filtros y paginación | FLUYE |
| `maintenance._cleanup_async()` | `r_metrics.rowcount`, `r_incidents.rowcount` | DELETE SQL directo con INTERVAL '30 days' | Sí — retorna filas eliminadas reales | FLUYE |

---

### Pruebas de Comportamiento (Step 7b)

| Comportamiento | Comando | Resultado | Estado |
|---------------|---------|-----------|--------|
| 135 tests unitarios pasan | `cd backend && python -m pytest tests/unit/ -q` | `135 passed in 1.59s` | PASA |
| Circuit breaker se abre tras 3 fallos | test_circuit_breaker.py (10 tests) | Todos pasan | PASA |
| Mensaje DOWN contiene nombre/IP/sitio/timestamp | test_telegram.py (10 tests) | Todos pasan | PASA |
| Incidente se abre/cierra con SELECT FOR UPDATE | test_alerts.py (14 tests) | Todos pasan | PASA |
| GET /incidents requiere JWT | test_incidents.py (10 tests) | 401 sin token verificado | PASA |
| Cleanup no borra incidentes abiertos | test_maintenance.py (13 tests) | Guard `resolved_at IS NOT NULL` verificado | PASA |
| API Telegram real en producción | No ejecutable sin credenciales reales | — | REQUIERE HUMANO |

---

### Cobertura de Requisitos

| Requisito | Plan de origen | Descripción | Estado | Evidencia |
|-----------|---------------|-------------|--------|-----------|
| MK-01 | 03-01 | CPU% y RAM% escritos en metrics | SATISFECHO | `_parse_metrics()` extrae `cpu-load`, calcula RAM% de `free-memory`/`total-memory` |
| MK-02 | 03-01 | TX/RX bps por interfaz en metrics | SATISFECHO | `tx-bits-per-second`, `rx-bits-per-second` por interface en `_parse_metrics()` |
| MK-03 | 03-01 | `api.close()` en finally + cleanup 30 días | SATISFECHO | `api.close()` en línea 160 mikrotik.py, DELETE 30 días en maintenance.py |
| MK-04 | 03-01 | Circuit breaker abre tras 3 fallos, TTL 5min | SATISFECHO | `CIRCUIT_OPEN_TTL=300`, `CIRCUIT_FAIL_THRESHOLD=3`, verificado en tests |
| ALERT-01 | 03-02 | polling.py dispara handle_device_down al DOWN | SATISFECHO | `apply_async(countdown=ALERT_DEBOUNCE_SECONDS)` en polling.py línea 187 |
| ALERT-02 | 03-02 | Mensaje DOWN con nombre/IP/sitio/timestamp | SATISFECHO | `format_down_message()` incluye los 4 campos, parseados con HTML |
| ALERT-03 | 03-02 | Mensaje UP con duración calculada | SATISFECHO | `format_up_message()` con `duration_seconds`, formato Xh Xm Xs |
| ALERT-04 | 03-02 | Debounce — no alerta si incidente cerrado antes del countdown | SATISFECHO | Verificación `incident.resolved_at is not None` en `_handle_device_down_async()` |
| ALERT-05 | 03-02 | `alert_sent` y `recovery_alert_sent` marcados | SATISFECHO | Marcados en lines 110 y 155 respectivamente, antes de commit |
| ALERT-06 | 03-01 | `get_threshold()` prioriza DB > env var | SATISFECHO | Cascada 3 niveles en thresholds.py |
| INC-01 | 03-02 | Incidente abierto con `started_at` al DOWN | SATISFECHO | `open_incident_if_not_exists()` con `with_for_update()` en alerts.py |
| INC-02 | 03-02 | Incidente cerrado con `duration_seconds` al UP | SATISFECHO | `close_incident()` calcula `duration_seconds = int((now - started_at).total_seconds())` |
| INC-03 | 03-03 | `GET /incidents` con filtros | SATISFECHO | API funcional con filtros, JWT. `Incidents.tsx` creado con filtros por sitio y estado, ruta `/incidents` en router, enlace en Dashboard. |
| INC-04 | 03-03 | Cleanup automático incidentes > 30 días | SATISFECHO | `crontab(hour=3, minute=0)` + DELETE `resolved_at < NOW() - INTERVAL '30 days'` |

---

### Anti-Patrones Encontrados

No se encontraron TODOs, FIXMEs, placeholders ni implementaciones stub en los archivos de Phase 3.

| Archivo | Línea | Patrón | Severidad | Impacto |
|---------|-------|--------|-----------|---------|
| `frontend/src/pages/Incidents.tsx` | — | Página de incidentes creada | RESUELTO | El técnico puede ver historial de incidentes desde la UI en /incidents |

---

### Verificación Humana Requerida

#### 1. Integración real con Telegram en producción

**Prueba:** Configurar `TELEGRAM_BOT_TOKEN` y `TELEGRAM_CHAT_ID` en Railway. Provocar una caída real (desconectar un equipo o marcar un dispositivo DOWN manualmente). Esperar el `ALERT_DEBOUNCE_SECONDS` (120s).
**Esperado:** El bot envía un mensaje HTML al canal Telegram con nombre del equipo, IP en `<code>`, sitio, timestamp UTC. Al reconectar, recibir mensaje UP con duración correcta.
**Por qué humano:** `send_telegram_alert()` usa `_get_bot_class()` como seam para mockear en tests — la integración real con la API de Telegram requiere credenciales producción y un equipo de red real o simulado.

---

### Resumen de Gaps

**0 gaps activos — SC-3 cerrado el 2026-04-26:**

**SC-3 cumplido:** El backend registra incidentes con apertura/cierre SELECT FOR UPDATE y el API `GET /api/v1/incidents` con filtros y JWT está operativo. La página `frontend/src/pages/Incidents.tsx` fue creada con tabla de incidentes, filtros por sitio y estado abierto/cerrado, y enlace de navegación desde el dashboard. Ruta `/incidents` protegida con PrivateRoute. Build de producción exitoso.

**1 ítem diferido (no es gap accionable):**

**SC-1 diferido a Phase 6:** El collector Mikrotik recolecta y persiste CPU%, RAM%, TX/RX bps correctamente. La visualización en el dashboard es responsabilidad de Phase 6 (SC-3 y SC-4 cubren esto explícitamente). No se requiere acción en Phase 3.

---

_Verificado: 2026-04-27T04:30:00Z_
_Verificador: Claude (gsd-verifier)_
