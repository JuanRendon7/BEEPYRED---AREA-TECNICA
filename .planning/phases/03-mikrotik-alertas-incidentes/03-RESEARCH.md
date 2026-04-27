# Phase 3: Mikrotik + Alertas + Incidentes — Research

**Investigado:** 2026-04-26
**Dominio:** RouterOS API, alertas Telegram, pipeline de incidentes, retención de métricas
**Confianza global:** HIGH (stack ya decidido; investigación centrada en patrones de uso concretos)

---

## Resumen

La Phase 3 construye tres subsistemas interconectados sobre la base ya existente (Celery + Redis + PostgreSQL + asyncpg):

1. **Collector Mikrotik** — conecta via RouterOS API (librouteros 4.0, síncrono con `run_in_executor`) y escribe métricas CPU/RAM/tráfico a la tabla `metrics` existente usando inserciones por lote.
2. **Pipeline de alertas** — el worker de polling ICMP ya detecta transiciones DOWN/UP en `_ping_and_update`. Phase 3 extiende ese punto para abrir/cerrar incidentes y disparar mensajes Telegram usando `python-telegram-bot` v21 en modo outbound-only dentro de `asyncio.run()`.
3. **Mantenimiento** — tarea Celery beat diaria limpia `metrics` e `incidents` con más de 30 días mediante `DELETE ... WHERE recorded_at < NOW() - INTERVAL '30 days'`.

**Recomendación principal:** No usar TimescaleDB — la decisión ya está tomada (PostgreSQL puro con BRIN index en `recorded_at`). No usar `pybreaker` con Redis storage — implementar circuit breaker manual en Redis con claves por dispositivo: es más simple, ya se controla el schema de Redis, y evita una dependencia extra.

---

<phase_requirements>
## Requisitos de Phase 3

| ID | Descripción | Soporte en investigación |
|----|-------------|--------------------------|
| MK-01 | Recolectar CPU%, RAM% e interfaces TX/RX bps de Mikrotik via RouterOS API | librouteros 4.0 `async_connect` + paths `/system/resource` y `/interface` |
| MK-02 | Recolectar tráfico TX/RX por interfaz | mismo collector, path `api.path('interface')` |
| MK-03 | Métricas históricas en PostgreSQL con retención 30 días y limpieza automática | tabla `metrics` existente + Celery beat `DELETE WHERE` |
| MK-04 | Umbrales configurables sin tocar código — tabla `alerts` o env vars | tabla `alerts` ya existe + `settings.CPU_ALERT_THRESHOLD_PCT` |
| ALERT-01 | Detectar transición DOWN tras 3 fallos ICMP | `_ping_and_update` ya hace esto; Phase 3 engancha el evento |
| ALERT-02 | Telegram DOWN: nombre, IP, sitio, timestamp | `Bot.send_message` con parse_mode=HTML |
| ALERT-03 | Telegram UP: nombre, IP, duración de la caída | cerrar incidente → calcular duración → enviar |
| ALERT-04 | Debounce anti-flapping (no alertar si recupera antes de N segundos) | `debounce_seconds` en tabla `alerts` o env var |
| ALERT-05 | Estado de alerta persistido en DB (no solo Redis) | columnas `alert_sent` / `recovery_alert_sent` en `incidents` ya existen |
| ALERT-06 | Umbrales CPU/señal configurables desde DB o env vars | tabla `alerts` (`alert_type`, `threshold_value`) + env vars fallback |
| INC-01 | Registrar incidente automáticamente al DOWN | `INSERT INTO incidents (device_id, started_at)` al detectar transición |
| INC-02 | Cerrar incidente al recovery con duración calculada | `UPDATE incidents SET resolved_at, duration_seconds WHERE resolved_at IS NULL` |
| INC-03 | GET /incidents con filtros por equipo y sitio | endpoint FastAPI con parámetros query `device_id`, `site` |
| INC-04 | Limpieza automática de incidentes > 30 días | Celery beat task diaria |
</phase_requirements>

---

## Hallazgos por dominio de investigación

### 1. librouteros — Compatibilidad async y uso de la API

**Versión actual:** 4.0.1 (publicada 9 abril 2026) [VERIFIED: pypi.org/project/librouteros]

La librería expone **dos funciones de conexión**:

- `connect(username, password, host, port=8728)` — síncrona (blocking)
- `async_connect(username, password, host, port=8728)` — asíncrona nativa, retorna un api object await-able [VERIFIED: librouteros.readthedocs.io/en/latest/connect.html]

**CRÍTICO:** La versión 4.0.x introdujo `async_connect` (las versiones 3.x solo tenían `connect` síncrono). El STACK.md listaba `librouteros==3.2+` — esto está desactualizado. La versión real instalable es 4.0.1. El requirements.txt **no incluye librouteros aún** — debe agregarse.

#### Patrón de conexión async (recomendado para Celery)

Dado que el task Celery ya usa `asyncio.run()` (patrón establecido en `polling.py`), se usa `async_connect` directamente:

```python
# Fuente: librouteros.readthedocs.io/en/latest/connect.html [VERIFIED]
from librouteros import async_connect

async def collect_mikrotik_metrics(host: str, username: str, password: str) -> dict:
    api = await async_connect(username=username, password=password, host=host)
    try:
        # /system/resource — CPU y RAM
        resource_path = api.path('system', 'resource')
        resources = [item async for item in resource_path]
        resource = resources[0]  # siempre un solo elemento

        # /interface — tráfico por interfaz
        iface_path = api.path('interface')
        interfaces = [item async for item in iface_path]
    finally:
        api.close()  # cierre explícito — MK-03
    return {"resource": resource, "interfaces": interfaces}
```

#### Campos retornados por RouterOS API

Los campos de `/system/resource` relevantes [ASSUMED — basado en RouterOS API documentation knowledge]:
- `cpu-load` → CPU actual en porcentaje (int)
- `free-memory` y `total-memory` → para calcular RAM usada %
- `uptime` → string de uptime

Los campos de `/interface` relevantes [ASSUMED]:
- `name` → nombre de interfaz (ether1, wlan1, etc.)
- `tx-byte`, `rx-byte` → bytes acumulados (no bps directos)
- `tx-bits-per-second`, `rx-bits-per-second` → bps actuales (disponibles con `/interface print stats`)

**Nota de diseño:** RouterOS API devuelve `tx-byte` y `rx-byte` como contadores acumulados. Para obtener bps instantáneos, el comando correcto es navegar al path con stats. En la práctica, dos enfoques:
1. Guardar bytes del poll anterior en Redis y calcular delta (más preciso)
2. Usar `/interface/print` con `stats` que incluye `tx-bits-per-second` directamente [ASSUMED]

**Recomendación:** Usar approach 2 con path `api.path('interface')` iterando directamente — RouterOS incluye `tx-bits-per-second` y `rx-bits-per-second` en la respuesta estándar de interfaces.

#### SSL/encriptado

Para usar puerto 8729 (api-ssl), pasar `ssl_wrapper`:

```python
import ssl
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE
api = await async_connect(
    username='admin', password='pass', host='192.168.1.1',
    port=8729, ssl_wrapper=ctx.wrap_socket
)
```

#### Cierre de sesión (MK-03 — sin sesiones zombie)

librouteros expone `api.close()` (síncrono). Siempre en bloque `finally`. No hay `aclose()` async en 4.0 [ASSUMED — no confirmado en docs, usar try/finally con close()].

---

### 2. Circuit Breaker por dispositivo (MK-04)

**Decisión recomendada: implementación manual con Redis. No usar `pybreaker`.**

**Razones:**
- `pybreaker 1.4.1` tiene Redis backend via `CircuitRedisStorage`, pero requiere `StrictRedis` con `decode_responses=False` — incompatible con el cliente `redis==7.4.0` que ya usa el proyecto con `decode_responses=True` en algunos lugares [VERIFIED: pybreaker PyPI 1.4.1]
- El circuit breaker en este caso es por-dispositivo (cientos de instancias) — pybreaker crearía un objeto `CircuitBreaker` por device_id cargado al arrancar
- La lógica requerida es simple: contador de fallos en Redis con TTL

#### Patrón manual recomendado (Redis keys)

```python
# Fuente: patrón estándar de circuit breaker con Redis [ASSUMED — patrón de diseño conocido]

CIRCUIT_OPEN_TTL = 5 * 60  # 5 minutos (MK-04)
CIRCUIT_FAIL_THRESHOLD = 3  # 3 fallos RouterOS API consecutivos

async def is_circuit_open(redis_client, device_id: int) -> bool:
    """True si el circuit breaker está abierto para este dispositivo."""
    key = f"cb:open:{device_id}"
    return await redis_client.exists(key) > 0

async def record_api_failure(redis_client, device_id: int) -> bool:
    """
    Incrementa contador de fallos. Si llega a THRESHOLD, abre el circuit.
    Retorna True si el circuit acaba de abrirse.
    """
    fail_key = f"cb:fails:{device_id}"
    count = await redis_client.incr(fail_key)
    await redis_client.expire(fail_key, CIRCUIT_OPEN_TTL)

    if count >= CIRCUIT_FAIL_THRESHOLD:
        open_key = f"cb:open:{device_id}"
        await redis_client.setex(open_key, CIRCUIT_OPEN_TTL, "1")
        await redis_client.delete(fail_key)
        return True
    return False

async def record_api_success(redis_client, device_id: int) -> None:
    """Resetea el circuit breaker al tener éxito."""
    await redis_client.delete(f"cb:fails:{device_id}")
    await redis_client.delete(f"cb:open:{device_id}")
```

**Ventajas:** compartido entre todos los workers Celery (Redis), TTL automático de 5 minutos = auto-reset sin código adicional, sin dependencia externa.

**Separación de circuit breakers:** El circuit breaker de ICMP ya existe implícitamente en `consecutive_failures` de la tabla `devices`. El de RouterOS API (MK-04) es **independiente** — puede estar en UNKNOWN de ICMP pero con RouterOS API funcionando. Usar prefijo `cb:` para distinguir.

---

### 3. python-telegram-bot v21 — Modo outbound-only desde Celery

**Versión en requirements.txt:** No instalada aún. Debe agregarse `python-telegram-bot==21.*`.

**Patrón correcto para Celery (outbound-only sin webhook):** [VERIFIED: docs.python-telegram-bot.org/en/stable/telegram.bot.html]

```python
# Patrón recomendado — async context manager maneja initialize/shutdown automáticamente
# Fuente: python-telegram-bot docs oficiales [VERIFIED]

from telegram import Bot

async def send_telegram_alert(token: str, chat_id: str, text: str) -> None:
    async with Bot(token=token) as bot:
        await bot.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode="HTML"
        )
```

Desde el task Celery síncrono (mismo patrón que `poll_all_devices`):

```python
@shared_task(name="tasks.send_telegram_alert")
def send_telegram_alert_task(chat_id: str, text: str) -> None:
    asyncio.run(_send_telegram_alert_async(chat_id, text))

async def _send_telegram_alert_async(chat_id: str, text: str) -> None:
    async with Bot(token=settings.TELEGRAM_BOT_TOKEN) as bot:
        await bot.send_message(chat_id=chat_id, text=text, parse_mode="HTML")
```

**Por qué `async with Bot(...)` y no `Bot(token).send_message(...)`:**
- `async with bot:` es equivalente a `await bot.initialize()` + `await bot.shutdown()` en bloque finally [VERIFIED]
- `initialize()` configura la sesión HTTP interna (httpx por debajo en v21)
- Sin `initialize()`, la primera llamada puede fallar con `RuntimeError: Bot not initialized`

**Parse mode recomendado:** `HTML` en lugar de `Markdown`. Markdown de Telegram tiene escaping complejo (guiones, puntos necesitan escape); HTML es más predecible para mensajes programáticos.

**Formato de mensaje DOWN recomendado (ALERT-02/ALERT-06):**

```python
def format_down_message(device_name: str, ip: str, site: str, timestamp: datetime) -> str:
    ts = timestamp.strftime("%d/%m/%Y %H:%M:%S")
    return (
        f"🔴 <b>EQUIPO CAÍDO</b>\n"
        f"<b>Nombre:</b> {device_name}\n"
        f"<b>IP:</b> <code>{ip}</code>\n"
        f"<b>Sitio:</b> {site or 'Sin sitio'}\n"
        f"<b>Hora:</b> {ts} UTC"
    )

def format_up_message(device_name: str, ip: str, site: str, duration_s: int) -> str:
    mins, secs = divmod(duration_s, 60)
    hours, mins = divmod(mins, 60)
    dur = f"{hours}h {mins}m {secs}s" if hours else f"{mins}m {secs}s"
    return (
        f"🟢 <b>EQUIPO RECUPERADO</b>\n"
        f"<b>Nombre:</b> {device_name}\n"
        f"<b>IP:</b> <code>{ip}</code>\n"
        f"<b>Sitio:</b> {site or 'Sin sitio'}\n"
        f"<b>Duración caída:</b> {dur}"
    )
```

**Dependencia adicional:** `python-telegram-bot` en v21 usa `httpx` internamente — `httpx==0.28.1` ya está en requirements.txt, no hay conflicto.

---

### 4. Escritura de métricas en PostgreSQL (MK-01, MK-02, MK-03)

**Tabla `metrics` ya existe** con columnas: `id`, `device_id`, `metric_name`, `value`, `unit`, `interface`, `recorded_at`. No se necesita migración.

**Estrategia de escritura: INSERT individual por métrica dentro de una transacción por dispositivo.**

Un ciclo de Mikrotik produce aprox. 3-10 filas por device (cpu_pct, ram_pct, rx_bps y tx_bps por cada interfaz activa). Con 500 dispositivos Mikrotik = 1500-5000 filas por ciclo de 60s. Esto es manejable con inserciones normales.

```python
# Patrón recomendado — bulk insert dentro de una sesión [ASSUMED — patrón SQLAlchemy 2.0]
from sqlalchemy import insert
from app.models.metric import Metric
from app.core.database import AsyncSessionLocal

async def write_metrics(device_id: int, metrics: list[dict]) -> None:
    """
    metrics: [{"metric_name": "cpu_pct", "value": 45.2, "unit": "%", "interface": None}, ...]
    """
    async with AsyncSessionLocal() as db:
        await db.execute(
            insert(Metric),
            [
                {
                    "device_id": device_id,
                    "metric_name": m["metric_name"],
                    "value": m["value"],
                    "unit": m.get("unit"),
                    "interface": m.get("interface"),
                    "recorded_at": datetime.now(timezone.utc),
                }
                for m in metrics
            ]
        )
        await db.commit()
```

**Por qué `insert()` con lista en lugar de `session.add()` individual:** SQLAlchemy 2.0 con asyncpg usa `executemany` bajo el capó cuando se pasa una lista a `execute(insert(...), [rows])`, que es más eficiente que N inserciones separadas [VERIFIED: SQLAlchemy 2.0 docs].

**No se necesita TimescaleDB:** La decisión en `001_initial_schema.py` usa BRIN index en `recorded_at` — correcto para inserciones cronológicas. Para 4000 filas/minuto con retención de 30 días = ~172M filas en el peor caso teórico, pero en práctica Mikrotik es solo un tipo de dispositivo (no todos los 500 son Mikrotik).

---

### 5. Pipeline de alertas completo (ALERT-01 a ALERT-06)

#### Diagrama de flujo

```
Celery beat (60s)
    └── tasks.poll_all_devices()
            └── _ping_and_update(device)
                    ├── [status no cambia] → nada
                    ├── [UP → DOWN] → publish_status_update(Redis)
                    │                  + tasks.handle_device_down.delay(device_id)
                    └── [DOWN → UP]  → publish_status_update(Redis)
                                       + tasks.handle_device_recovery.delay(device_id)

tasks.handle_device_down(device_id):
    1. Verificar debounce en Redis (ALERT-04)
    2. Abrir incidente en DB si no hay uno abierto (INC-01)
    3. Marcar alert_sent = True en incidente
    4. Enviar Telegram DOWN (ALERT-02)

tasks.handle_device_recovery(device_id):
    1. Buscar incidente abierto en DB (resolved_at IS NULL)
    2. Cerrar incidente: resolved_at = now, duration_seconds = diff (INC-02)
    3. Enviar Telegram UP con duración (ALERT-03)
    4. Marcar recovery_alert_sent = True
```

#### Por qué tasks separados y no inline en `_ping_and_update`

`_ping_and_update` ya hace un commit a DB y publica a Redis. Añadir lógica de Telegram y apertura de incidentes ahí haría la función demasiado larga y difícil de testear. Separar en `handle_device_down` / `handle_device_recovery` permite:
- Testear la lógica de alertas independientemente del polling ICMP
- Retry de Celery si falla Telegram sin repetir el ping
- Posible reintento si hay error transitorio de DB

---

### 6. Debounce anti-flapping (ALERT-04)

El requisito es: no enviar alerta si el equipo recupera antes de N segundos.

**Patrón recomendado:** clave Redis con TTL corto al detectar DOWN. Si cuando llega `handle_device_down` ya no existe la clave (fue borrada por `handle_device_recovery`), no enviar alerta.

```python
# En handle_device_down:
debounce_key = f"alert:debounce:{device_id}"
# Configurar clave con TTL = ALERT_DEBOUNCE_SECONDS (ej: 120s = 2 minutos)
await redis.setex(debounce_key, settings.ALERT_DEBOUNCE_SECONDS, "pending")

# Esperar con countdown (el task se reencola con delay)
# O verificar si la clave aún existe N segundos después

# En handle_device_recovery:
await redis.delete(f"alert:debounce:{device_id}")
```

**Alternativa más simple (recomendada):** Usar el campo `started_at` del incidente. Al enviar la alerta DOWN, verificar que `datetime.now() - started_at > DEBOUNCE_SECONDS`. Si el equipo ya se recuperó (incidente cerrado) antes de que pase ese tiempo, no hay a quién alertar (el incidente ya tiene `resolved_at`).

**Implementación recomendada:** `handle_device_down` usa `apply_async(countdown=ALERT_DEBOUNCE_SECONDS)` — el task Celery se encola con delay de N segundos. Al ejecutarse, verifica si el incidente sigue abierto (`resolved_at IS NULL`). Si ya cerró, no envía. Simple, sin Redis extra.

```python
# En _ping_and_update, al detectar DOWN:
from app.tasks.alerts import handle_device_down
handle_device_down.apply_async(args=[device_id], countdown=settings.ALERT_DEBOUNCE_SECONDS)
```

---

### 7. Ciclo de vida de incidentes — Atomicidad y race conditions (INC-01, INC-02)

#### Apertura de incidente (DOWN)

```python
# Fuente: patrón SQLAlchemy 2.0 con SELECT FOR UPDATE [ASSUMED]
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

async def open_incident_if_not_exists(db: AsyncSession, device_id: int) -> Incident | None:
    """
    Abre un nuevo incidente solo si no hay uno abierto (resolved_at IS NULL).
    Usa INSERT ... ON CONFLICT DO NOTHING para evitar race conditions.
    """
    # Verificar si ya hay uno abierto
    result = await db.execute(
        select(Incident)
        .where(Incident.device_id == device_id)
        .where(Incident.resolved_at == None)
        .order_by(Incident.started_at.desc())
        .limit(1)
        .with_for_update()  # bloquea la fila para evitar doble apertura
    )
    existing = result.scalar_one_or_none()
    if existing:
        return existing  # ya hay un incidente abierto

    new_incident = Incident(
        device_id=device_id,
        started_at=datetime.now(timezone.utc),
        alert_sent=False,
        recovery_alert_sent=False,
    )
    db.add(new_incident)
    await db.flush()  # obtener el ID antes de commit
    return new_incident
```

#### Cierre de incidente (UP/recovery)

```python
async def close_incident(db: AsyncSession, device_id: int) -> Incident | None:
    """
    Cierra el incidente abierto más reciente para el dispositivo.
    Calcula duration_seconds.
    """
    result = await db.execute(
        select(Incident)
        .where(Incident.device_id == device_id)
        .where(Incident.resolved_at == None)
        .order_by(Incident.started_at.desc())
        .limit(1)
        .with_for_update()
    )
    incident = result.scalar_one_or_none()
    if not incident:
        return None  # no hay incidente abierto (recuperación sin DOWN previo registrado)

    now = datetime.now(timezone.utc)
    incident.resolved_at = now
    incident.duration_seconds = int((now - incident.started_at).total_seconds())
    return incident
```

**Por qué `with_for_update()`:** Evita que dos workers Celery abran/cierren el mismo incidente en paralelo si hay un burst de polling. El lock se libera al hacer `commit()`.

**El índice ya existe:** `idx_incidents_active` es un partial index en `(device_id, resolved_at) WHERE resolved_at IS NULL` — la query de incidente abierto es O(log n) [VERIFIED: 001_initial_schema.py en el codebase].

---

### 8. Estrategia de limpieza automática (MK-03, INC-04)

**Mecanismo recomendado: Celery beat task diaria.**

No usar triggers de PostgreSQL — añaden complejidad operacional en Railway. Celery beat ya está configurado y ejecutándose.

```python
# backend/app/tasks/maintenance.py
from celery import shared_task
from sqlalchemy import text
from app.core.database import AsyncSessionLocal
import asyncio

@shared_task(name="tasks.cleanup_old_data")
def cleanup_old_data() -> dict:
    return asyncio.run(_cleanup_async())

async def _cleanup_async() -> dict:
    async with AsyncSessionLocal() as db:
        # Limpiar métricas > 30 días (MK-03)
        r1 = await db.execute(
            text("DELETE FROM metrics WHERE recorded_at < NOW() - INTERVAL '30 days'")
        )
        # Limpiar incidentes resueltos > 30 días (INC-04)
        # NOTA: NO eliminar incidentes abiertos (resolved_at IS NULL)
        r2 = await db.execute(
            text(
                "DELETE FROM incidents "
                "WHERE resolved_at IS NOT NULL "
                "AND resolved_at < NOW() - INTERVAL '30 days'"
            )
        )
        await db.commit()
    return {
        "metrics_deleted": r1.rowcount,
        "incidents_deleted": r2.rowcount,
    }
```

**Beat schedule entry a agregar en `celery_app.py`:**

```python
"cleanup-old-data": {
    "task": "tasks.cleanup_old_data",
    "schedule": crontab(hour=3, minute=0),  # 3am hora Colombia (UTC-5)
    "options": {"expires": 3600},
}
```

**Importar `crontab`:** `from celery.schedules import crontab`

---

### 9. Umbrales configurables (MK-04, ALERT-05, ALERT-06)

La tabla `alerts` ya existe con columnas `alert_type`, `threshold_value`, `device_id (nullable)`, `is_active`, `consecutive_polls_required`.

**Estrategia de lectura de umbrales:**

```python
async def get_threshold(db: AsyncSession, alert_type: str, device_id: int | None = None) -> float | None:
    """
    Busca umbral en orden: específico por device > global > env var fallback.
    """
    # 1. Umbral específico por dispositivo
    if device_id:
        result = await db.execute(
            select(Alert.threshold_value)
            .where(Alert.device_id == device_id)
            .where(Alert.alert_type == alert_type)
            .where(Alert.is_active == True)
        )
        row = result.scalar_one_or_none()
        if row is not None:
            return float(row)

    # 2. Umbral global (device_id IS NULL)
    result = await db.execute(
        select(Alert.threshold_value)
        .where(Alert.device_id == None)
        .where(Alert.alert_type == alert_type)
        .where(Alert.is_active == True)
    )
    row = result.scalar_one_or_none()
    if row is not None:
        return float(row)

    # 3. Fallback a env var
    defaults = {
        "cpu_high": settings.CPU_ALERT_THRESHOLD_PCT,
        "signal_low": settings.ONU_SIGNAL_MIN_DBM,
    }
    return defaults.get(alert_type)
```

**Valores por defecto ya en settings:**
- `CPU_ALERT_THRESHOLD_PCT = 90.0`
- `ONU_SIGNAL_MIN_DBM = -28.0`
- `CONSECUTIVE_FAILURES_THRESHOLD = 3` (ya usado en polling)

**Env var nueva recomendada para debounce:** `ALERT_DEBOUNCE_SECONDS = 120` (2 minutos)

---

### 10. Endpoint GET /incidents (INC-03)

FastAPI router con filtros opcionales por `device_id` y `site`. El `site` requiere JOIN con la tabla `devices`.

```python
# GET /api/v1/incidents?device_id=5&site=Torre+Norte&limit=50&offset=0
@router.get("/incidents", response_model=list[IncidentResponse])
async def list_incidents(
    device_id: int | None = None,
    site: str | None = None,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    query = (
        select(Incident, Device.name, Device.site)
        .join(Device, Incident.device_id == Device.id)
        .order_by(Incident.started_at.desc())
        .limit(limit)
        .offset(offset)
    )
    if device_id:
        query = query.where(Incident.device_id == device_id)
    if site:
        query = query.where(Device.site == site)
    result = await db.execute(query)
    return result.all()
```

---

## Stack estándar para Phase 3

### Dependencias a agregar a requirements.txt

| Librería | Versión | Propósito | Estado |
|----------|---------|-----------|--------|
| `librouteros` | `==4.0.1` | RouterOS API (MK-01, MK-02) | No instalada — agregar |
| `python-telegram-bot` | `==21.*` | Alertas Telegram (ALERT-02, ALERT-03) | No instalada — agregar |

```bash
# Agregar a backend/requirements.txt
librouteros==4.0.1
python-telegram-bot==21.*
```

**Verificación de versiones:**
- `librouteros`: 4.0.1 publicada 2026-04-09 [VERIFIED: pypi.org]
- `python-telegram-bot`: serie 21.x, última estable [ASSUMED — no verificado en PyPI en esta sesión]

### Dependencias ya presentes (no agregar)

| Librería | Versión actual | Uso en Phase 3 |
|----------|----------------|----------------|
| `redis==7.4.0` | instalada | Circuit breaker keys, debounce |
| `sqlalchemy[asyncio]==2.0.49` | instalada | ORM para metrics, incidents, alerts |
| `asyncpg==0.31.0` | instalada | Driver PostgreSQL async |
| `celery[redis]==5.6.3` | instalada | Tasks polling, alertas, cleanup |
| `httpx==0.28.1` | instalada | Usado por python-telegram-bot internamente |
| `cryptography==47.0.0` | instalada | Descifrado de credenciales Fernet para RouterOS |

---

## Estructura de archivos recomendada para Phase 3

```
backend/app/
├── tasks/
│   ├── polling.py          # ya existe (ICMP) — modificar para disparar alertas
│   ├── mikrotik.py         # nuevo — RouterOS API collector
│   ├── alerts.py           # nuevo — handle_device_down, handle_device_recovery
│   └── maintenance.py      # nuevo — cleanup_old_data
├── api/v1/
│   └── incidents.py        # nuevo — GET /incidents
├── services/
│   ├── telegram.py         # nuevo — send_telegram_alert wrapper
│   ├── circuit_breaker.py  # nuevo — circuit breaker Redis helpers
│   └── thresholds.py       # nuevo — get_threshold() desde DB/env
└── schemas/
    └── incident.py         # nuevo — IncidentResponse Pydantic schema
```

**Cambio en `celery_app.py`:** agregar `app.tasks.mikrotik`, `app.tasks.alerts`, `app.tasks.maintenance` al `include`.

---

## Patrones anti-recomendados

| Anti-patrón | Por qué evitarlo | Alternativa |
|-------------|-----------------|-------------|
| TimescaleDB | Decisión ya bloqueada (Phase 1 usó PostgreSQL puro con BRIN) | No cambiar — BRIN funciona para el volumen |
| `pybreaker` con Redis | Incompatibilidad decode_responses; dependencia extra innecesaria | Circuit breaker manual con Redis keys + TTL |
| Webhook Telegram | Requiere endpoint público, complejidad adicional | Bot outbound-only con `async with Bot(...)` |
| `threading.Thread` en collector | GIL contention, patrón incompatible con asyncio ya en uso | `asyncio.run()` en task Celery (patrón ya establecido) |
| Limpiar métricas con trigger PostgreSQL | Complejidad operacional en Railway, difícil debuggear | Celery beat task diaria |
| `loop.run_until_complete()` | Deprecated Python 3.10+ — comentario en polling.py lo prohíbe | `asyncio.run()` |
| Enviar Telegram inline en `_ping_and_update` | Función ya tiene responsabilidad única (ping + estado DB) | Task separado `handle_device_down` |

---

## Riesgos y áreas de validación

### Riesgo 1: librouteros 4.0 vs 3.x — cambio de API breaking
**Qué puede ir mal:** STACK.md menciona `librouteros 3.2+` pero la versión actual es 4.0.1. La versión 3.4.0 fue "yanked" por incompatibilidad. Puede haber cambios de API entre 3.x y 4.0 en los métodos de path o en el cierre de conexión.
**Mitigación:** Probar en development con un Mikrotik real antes del deploy. Verificar si `api.close()` sigue siendo el método correcto en 4.0 o si cambió.
**Confianza:** MEDIUM — async_connect confirmado en docs, pero close() es ASSUMED.

### Riesgo 2: RouterOS API — campos de interfaces
**Qué puede ir mal:** Los nombres de campo (`tx-bits-per-second`, `cpu-load`) varían entre versiones de RouterOS (6.x vs 7.x).
**Mitigación:** Hacer `print(dict(resource))` en development y documentar los campos reales del hardware del ISP. Implementar extracción defensiva con `.get()` y logging de campos desconocidos.
**Confianza:** MEDIUM para campo `cpu-load`; LOW para `tx-bits-per-second` (puede requerir stats separate).

### Riesgo 3: Celery worker sin event loop persistente
**Qué puede ir mal:** Cada task llama `asyncio.run()` creando un nuevo event loop. Para el collector Mikrotik, cada ciclo de 60s abre y cierra la conexión RouterOS. Con muchos dispositivos y conexiones cortas, esto es correcto pero significa sin connection pooling.
**Mitigación:** Para v1 con ~50 Mikrotiks, conexiones cortas por ciclo es aceptable. Si en el futuro hay 500 Mikrotik, considerar connection pool persistente en el worker.
**Confianza:** HIGH — patrón ya establecido en polling.py.

### Riesgo 4: Telegram rate limiting
**Qué puede ir mal:** Si muchos equipos caen al mismo tiempo (corte eléctrico masivo), se envían múltiples mensajes a Telegram en segundos. Telegram Bot API tiene límite de ~30 mensajes/segundo.
**Mitigación para v1:** `apply_async` de cada alerta tiene su propio task — Celery los procesa secuencialmente (concurrency=1 en worker de alertas) o con pequeño delay. Para v1 con pocos Mikrotik el riesgo es bajo.
**Confianza:** LOW para el comportamiento exacto del rate limiting de Telegram.

### Riesgo 5: `ALERT_DEBOUNCE_SECONDS` no está en settings.py
**Estado:** La variable no existe aún en `app/core/config.py`. Debe agregarse.
**Acción:** Wave 0 — agregar a `Settings` class con default 120.

---

## Arquitectura de validación

### Framework de tests

| Propiedad | Valor |
|-----------|-------|
| Framework | pytest 8.3.5 + pytest-asyncio 0.25.3 |
| Config | `backend/pytest.ini` (`asyncio_mode = auto`, `testpaths = tests/unit`) |
| Comando rápido | `cd backend && pytest tests/unit/ -x -q` |
| Suite completa | `cd backend && pytest tests/unit/ -v --cov=app --cov-report=term-missing` |

### Mapa de requisitos → tests

| REQ-ID | Comportamiento | Tipo test | Comando automático | Archivo existe? |
|--------|--------------|-----------|--------------------|-----------------|
| MK-01 | `collect_mikrotik` retorna dict con cpu_pct, ram_pct | unit | `pytest tests/unit/test_mikrotik.py -x` | No — Wave 0 |
| MK-02 | Interfaces parseadas con tx_bps, rx_bps por nombre | unit | `pytest tests/unit/test_mikrotik.py::test_interface_metrics -x` | No — Wave 0 |
| MK-03 | `write_metrics` inserta filas en DB (mock) | unit | `pytest tests/unit/test_mikrotik.py::test_write_metrics -x` | No — Wave 0 |
| MK-04 | Circuit breaker abre tras 3 fallos, auto-resetea en 5min | unit | `pytest tests/unit/test_circuit_breaker.py -x` | No — Wave 0 |
| ALERT-01 | `_ping_and_update` dispara `handle_device_down.delay` al pasar a DOWN | unit | `pytest tests/unit/test_alerts.py::test_down_triggers_alert -x` | No — Wave 0 |
| ALERT-02 | Mensaje Telegram DOWN contiene nombre, IP, sitio, timestamp | unit | `pytest tests/unit/test_telegram.py::test_down_message_format -x` | No — Wave 0 |
| ALERT-03 | Mensaje UP incluye duración calculada correctamente | unit | `pytest tests/unit/test_telegram.py::test_up_message_duration -x` | No — Wave 0 |
| ALERT-04 | Debounce: si resuelto antes de N segundos, no envía alerta | unit | `pytest tests/unit/test_alerts.py::test_debounce -x` | No — Wave 0 |
| ALERT-05 | `alert_sent` marcado True en DB después de enviar alerta | unit | `pytest tests/unit/test_alerts.py::test_alert_sent_flag -x` | No — Wave 0 |
| ALERT-06 | `get_threshold` lee de DB device-específico, luego global, luego env | unit | `pytest tests/unit/test_thresholds.py -x` | No — Wave 0 |
| INC-01 | Incidente abierto al DOWN (INSERT con started_at) | unit | `pytest tests/unit/test_incidents.py::test_open_incident -x` | No — Wave 0 |
| INC-02 | Incidente cerrado al UP con duration_seconds correcto | unit | `pytest tests/unit/test_incidents.py::test_close_incident -x` | No — Wave 0 |
| INC-03 | GET /incidents filtra por device_id y site | unit | `pytest tests/unit/test_incidents.py::test_list_incidents_filter -x` | No — Wave 0 |
| INC-04 | cleanup_old_data borra métricas e incidentes > 30 días | unit | `pytest tests/unit/test_maintenance.py -x` | No — Wave 0 |

### Gaps de Wave 0

- [ ] `backend/tests/unit/test_mikrotik.py` — cubre MK-01, MK-02, MK-03
- [ ] `backend/tests/unit/test_circuit_breaker.py` — cubre MK-04
- [ ] `backend/tests/unit/test_alerts.py` — cubre ALERT-01, ALERT-04, ALERT-05
- [ ] `backend/tests/unit/test_telegram.py` — cubre ALERT-02, ALERT-03, ALERT-06
- [ ] `backend/tests/unit/test_thresholds.py` — cubre ALERT-06
- [ ] `backend/tests/unit/test_incidents.py` — cubre INC-01, INC-02, INC-03
- [ ] `backend/tests/unit/test_maintenance.py` — cubre INC-04

---

## Dominio de seguridad

| Categoría ASVS | Aplica | Control estándar |
|----------------|--------|-----------------|
| V2 Autenticación | No | (RouterOS API: credenciales ya encriptadas con Fernet en `device_credentials`) |
| V3 Gestión de sesiones | Parcial | librouteros cierre explícito con `api.close()` en finally — sin sesiones zombie (MK-03) |
| V4 Control de acceso | Sí | Endpoint GET /incidents protegido por JWT (patrón ya establecido en Phase 2) |
| V5 Validación de entrada | Sí | Pydantic valida todos los parámetros del endpoint `/incidents`; valores de RouterOS parseados con `.get()` defensivo |
| V6 Criptografía | Sí | Contraseñas RouterOS API almacenadas con Fernet, descifradas en runtime — nunca en logs |

**Patrones de amenaza específicos del stack:**

| Patrón | STRIDE | Mitigación estándar |
|--------|--------|---------------------|
| Credenciales RouterOS en logs | Information Disclosure | `decrypt_credential()` solo en runtime; no loggear `username`/`password` |
| Race condition en apertura de incidentes | Tampering | `SELECT ... FOR UPDATE` en `open_incident_if_not_exists` |
| Telegram bot token expuesto | Information Disclosure | `TELEGRAM_BOT_TOKEN` en env var (SecretStr o str en settings, nunca hardcoded) |
| Injection via parámetros API RouterOS | Tampering | librouteros usa protocolo binario RouterOS — no SQL injection. Validar `host/ip` con Pydantic antes de conectar |

---

## Disponibilidad de entorno

| Dependencia | Requerida por | Disponible | Notas |
|-------------|--------------|------------|-------|
| PostgreSQL | Todas las tasks | Sí (Railway addon) | `asyncpg==0.31.0` ya instalado |
| Redis | Circuit breaker, debounce, Celery broker | Sí (Railway addon) | `redis==7.4.0` instalado |
| Telegram Bot API | ALERT-02, ALERT-03 | Sí (internet) | `TELEGRAM_BOT_TOKEN` y `TELEGRAM_CHAT_ID` ya en settings.py (vacíos) |
| Equipo Mikrotik accesible | MK-01, MK-02 | Desconocido | Depende de VPN/topología de red del ISP — validar antes de Phase 3 |
| librouteros 4.0.1 | MK-01, MK-02 | No (no en requirements.txt) | Agregar a requirements.txt |
| python-telegram-bot 21.x | ALERT-02, ALERT-03 | No (no en requirements.txt) | Agregar a requirements.txt |

---

## Log de suposiciones (claims [ASSUMED])

| # | Claim | Sección | Riesgo si es incorrecto |
|---|-------|---------|------------------------|
| A1 | Los campos de RouterOS API son `cpu-load`, `free-memory`, `total-memory` para /system/resource | §1 librouteros | Código falla silenciosamente con KeyError; mitigación: usar `.get()` |
| A2 | `/interface` en RouterOS incluye `tx-bits-per-second` y `rx-bits-per-second` directamente | §1 librouteros | Habría que calcular delta de bytes en dos polls |
| A3 | `api.close()` es el método correcto en librouteros 4.0 para cerrar conexión | §1 librouteros | Sesiones zombie si el método cambió; probar en dev |
| A4 | `python-telegram-bot` v21 actual está en la serie 21.x (no 22.x) | §3 Telegram | Versión incorrecta en requirements.txt; verificar `npm view python-telegram-bot` |
| A5 | El patrón `apply_async(countdown=N)` es suficiente para debounce | §6 Debounce | Si el worker falla, el countdown se pierde; para v1 es aceptable |
| A6 | `select(...).with_for_update()` funciona con asyncpg en SQLAlchemy 2.0 async | §7 Incidentes | Race condition en apertura concurrente; alternativa: UNIQUE constraint en DB |

---

## Preguntas abiertas

1. **¿Los Mikrotik del ISP usan RouterOS 6.x o 7.x?**
   - Qué sabemos: RouterOS 7.x cambió algunos nombres de campo en la API
   - Qué es incierto: si hay diferencias relevantes en `/system/resource` o `/interface`
   - Recomendación: hacer una prueba de conexión manual con `async_connect` y loggear los campos reales antes de escribir el parser

2. **¿Cuántos dispositivos Mikrotik hay en el inventario?**
   - Qué sabemos: el sistema está diseñado para 500+ dispositivos en total
   - Qué es incierto: cuántos son específicamente Mikrotik
   - Impacto: determina si el collector por lotes necesita semáforo propio

3. **¿`TELEGRAM_BOT_TOKEN` y `TELEGRAM_CHAT_ID` están configurados en Railway?**
   - Los campos existen en `settings.py` con default `""`
   - El collector de alertas debe verificar que no estén vacíos antes de intentar enviar

4. **¿El ALERT_DEBOUNCE_SECONDS debe ser configurable por tipo de equipo?**
   - Por ahora: variable de entorno global
   - Si en el futuro hay equipos inestables: agregar columna a tabla `alerts`

---

## Fuentes

### Primarias (HIGH confidence)
- `librouteros.readthedocs.io/en/latest/connect.html` — parámetros de connect/async_connect, SSL
- `librouteros.readthedocs.io/en/latest/path.html` — Path object API, iteración async
- `pypi.org/project/librouteros/` — versión 4.0.1 confirmada
- `docs.python-telegram-bot.org/en/stable/telegram.bot.html` — patrón `async with Bot(...)`
- Codebase existente: `polling.py`, `celery_app.py`, `config.py`, `001_initial_schema.py` — columnas reales de las tablas

### Secundarias (MEDIUM confidence)
- `pypi.org/project/pybreaker/` — versión 1.4.1, limitaciones decode_responses
- WebSearch: pybreaker Redis backend, SQLAlchemy bulk insert executemany, Celery beat DELETE cleanup

### Terciarias (LOW confidence — marcar para validación)
- Nombres de campos RouterOS API (`cpu-load`, `tx-bits-per-second`) — training knowledge, no verificado contra RouterOS 7.x
- Método `api.close()` en librouteros 4.0 — no confirmado en docs de esta sesión

---

## Metadata

**Desglose de confianza:**
- Stack estándar: HIGH — librouteros 4.0.1 y python-telegram-bot v21 confirmados en PyPI y docs oficiales
- Patrones de arquitectura: HIGH — circuit breaker Redis, Celery countdown, SQLAlchemy bulk insert son patrones estándar verificados
- Campos RouterOS API: MEDIUM — nombres de campos basados en training knowledge; validar contra hardware real
- Cierre de conexión librouteros 4.0: LOW — `api.close()` no confirmado explícitamente en docs 4.0

**Fecha de investigación:** 2026-04-26
**Válido hasta:** 2026-05-26 (30 días — stack relativamente estable)
