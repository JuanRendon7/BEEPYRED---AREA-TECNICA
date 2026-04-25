# Architecture Patterns

**Domain:** NOC web — monitoreo de red ISP con 500+ equipos heterogéneos
**Researched:** 2026-04-25
**Confidence overall:** HIGH (patrones establecidos en sistemas como LibreNMS, Zabbix, Netdata, y proyectos ISP similares)

---

## Recommended Architecture

### Decisión fundamental: Monolito modular, NO microservicios

**Veredicto:** Monolito modular deployado en Railway con un proceso worker separado.

**Razón:** Microservicios requieren orquestación (Kubernetes), service mesh, distributed tracing, y complejidad operacional innecesaria para un equipo de uno. El problema real es concurrencia de I/O (polling 500 equipos) — no distribución de carga computacional. Un monolito modular con worker pool async resuelve exactamente eso.

**No usar microservicios porque:**
- Railway cobra por servicio activo; cada microservicio = costo extra
- Sin beneficio real a esta escala (500 equipos, 1 técnico, polling cada 30-60s)
- Debugging distribuido es significativamente más costoso que debugging monolítico
- La complejidad del dominio ya es alta (4 protocolos distintos); no sumar complejidad de infra

**Estructura de deployment en Railway:**
```
Railway Project: beepyred-noc
├── Service: web          (FastAPI — API REST + WebSocket server)
├── Service: worker       (Celery beat + workers — polling engine)
├── Service: redis        (Railway managed Redis — task queue + pub/sub)
└── Service: postgres     (Railway managed PostgreSQL — inventory + history)
```

TimescaleDB como extensión de PostgreSQL (no servicio separado). Railway managed Postgres soporta extensiones; TimescaleDB está disponible en instancias dedicadas o se puede usar pgvector/extensiones custom si la versión no lo soporta. Alternativa: tabla BRIN-indexed en Postgres puro (igualmente eficiente a esta escala).

---

## Component Boundaries

### Mapa de componentes

```
┌─────────────────────────────────────────────────────────────────┐
│                         BROWSER (Técnico)                        │
│   Dashboard SPA (React/Svelte) — polling SSE o WebSocket        │
└──────────────────────────┬──────────────────────────────────────┘
                           │ HTTPS / WebSocket
┌──────────────────────────▼──────────────────────────────────────┐
│                       WEB SERVICE (FastAPI)                      │
│                                                                   │
│  ┌──────────────┐  ┌──────────────┐  ┌─────────────────────┐   │
│  │  REST API    │  │ WebSocket /  │  │  Auth middleware     │   │
│  │  /devices    │  │  SSE /stream │  │  (JWT simple)        │   │
│  │  /alerts     │  │              │  │                       │   │
│  │  /history    │  └──────┬───────┘  └─────────────────────┘   │
│  └──────┬───────┘         │                                      │
└─────────┼─────────────────┼────────────────────────────────────┘
          │ SQL              │ Subscribe
          │                  │
┌─────────▼──────┐  ┌────────▼────────────────────────────────────┐
│   POSTGRESQL   │  │                  REDIS                        │
│                │  │                                               │
│  • devices     │  │  • Task queue  (Celery broker)               │
│  • metrics     │  │  • Pub/Sub     (metric updates → SSE)        │
│  • alerts      │  │  • Cache       (last known state por device) │
│  • incidents   │  │                                              │
└─────────┬──────┘  └──────────────────┬──────────────────────────┘
          │ Write                        │ Enqueue / Publish
          │                              │
┌─────────▼──────────────────────────────▼──────────────────────┐
│                      WORKER SERVICE (Celery)                    │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                  Scheduler (Celery Beat)                  │   │
│  │  Every 30s: enqueue poll tasks for all active devices    │   │
│  └──────────────────────────┬──────────────────────────────┘   │
│                              │                                    │
│  ┌───────────────────────────▼──────────────────────────────┐  │
│  │              Worker Pool (N concurrent workers)           │  │
│  │                                                            │  │
│  │  ┌────────────┐  ┌────────────┐  ┌────────────┐          │  │
│  │  │  Mikrotik  │  │  VSOL OLT  │  │  Ubiquiti  │  ...     │  │
│  │  │  Collector │  │  Collector │  │  Collector │          │  │
│  │  └────────────┘  └────────────┘  └────────────┘          │  │
│  │                                                            │  │
│  │         ↑ cada collector implementa la misma interfaz     │  │
│  └────────────────────────────────────────────────────────--─┘  │
│                                                                   │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │              Alert Engine (post-poll hook)                  │ │
│  │  Evalúa umbrales → genera Alert → notifica Telegram        │ │
│  └────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────┘
                              │ SSH / API / REST / Telnet
              ┌───────────────┼───────────────────────────┐
              │               │                            │
    ┌─────────▼──┐  ┌─────────▼──┐  ┌──────────▼──┐  ┌───▼────────┐
    │  Mikrotik  │  │ OLT VSOL   │  │  Ubiquiti   │  │  Mimosa    │
    │ RouterOS   │  │ SSH/Telnet │  │  UISP API   │  │  REST API  │
    │ API :8728  │  │            │  │  / SSH      │  │            │
    └────────────┘  └────────────┘  └─────────────┘  └────────────┘
```

---

## Component Responsibilities

| Componente | Responsabilidad | Comunica con |
|------------|-----------------|--------------|
| **Web Service (FastAPI)** | Servir API REST e inventario; mantener conexiones WebSocket/SSE activas; autenticar requests | PostgreSQL (lectura), Redis (subscribe pub/sub), Browser |
| **Worker Service (Celery)** | Ejecutar polling concurrente; normalizar métricas; escribir a DB; publicar updates | Redis (broker + publish), PostgreSQL (write), Equipos de red (TCP/SSH/HTTP) |
| **Celery Beat (Scheduler)** | Generar tareas de polling cada 30s por dispositivo activo | Redis (enqueue) |
| **Collector Layer** | Abstraer protocolo: cada tipo de equipo tiene su propia clase collector | Equipos de red; devuelve `DeviceMetrics` normalizado al Worker |
| **Alert Engine** | Post-proceso tras cada poll: comparar contra umbrales, crear incidents, disparar Telegram | PostgreSQL (read/write alerts), Telegram Bot API |
| **Redis Cache** | Mantener "last known state" por device\_id; sirve al frontend cuando el poll no ha corrido aún | Worker (write), Web Service (read) |
| **PostgreSQL** | Fuente de verdad: inventario de equipos, métricas históricas, alertas, incidentes | Worker (write), Web Service (read) |
| **Browser SPA** | Dashboard; recibe actualizaciones vía SSE o WebSocket; no hace polling directo a equipos | Web Service únicamente |

---

## Collector Layer — Diseño de la abstracción de protocolos

### Principio clave: Protocol Adapter Pattern

Cada tipo de equipo implementa la misma interfaz `BaseCollector`. El Worker no sabe qué protocolo usa — solo llama a `collect()` y recibe un `DeviceMetrics` normalizado.

```python
# Interfaz abstracta — el contrato que todo collector respeta
class BaseCollector(ABC):
    def __init__(self, device: Device):
        self.device = device

    @abstractmethod
    async def collect(self) -> DeviceMetrics:
        """Conectar al equipo, extraer métricas, retornar normalizado."""
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        """Ping/reachability check rápido antes del collect completo."""
        ...

# Implementaciones concretas — una por tipo de equipo
class MikrotikCollector(BaseCollector):
    """RouterOS API vía librouteros o routeros-api (Python)"""
    async def collect(self) -> DeviceMetrics: ...

class VSOLCollector(BaseCollector):
    """SSH/Telnet con asyncssh; parsea output de comandos CLI"""
    async def collect(self) -> DeviceMetrics: ...

class UbiquitiCollector(BaseCollector):
    """UISP REST API o SSH a AirOS; preferir UISP cuando disponible"""
    async def collect(self) -> DeviceMetrics: ...

class MimosaCollector(BaseCollector):
    """REST API nativa de Mimosa"""
    async def collect(self) -> DeviceMetrics: ...

# Registry — desacopla la selección del collector del resto del sistema
COLLECTOR_REGISTRY = {
    DeviceType.MIKROTIK:  MikrotikCollector,
    DeviceType.VSOL_OLT:  VSOLCollector,
    DeviceType.UBIQUITI:  UbiquitiCollector,
    DeviceType.MIMOSA:    MimosaCollector,
}

def get_collector(device: Device) -> BaseCollector:
    cls = COLLECTOR_REGISTRY[device.type]
    return cls(device)
```

### DeviceMetrics — el modelo normalizado

```python
@dataclass
class DeviceMetrics:
    device_id: str
    collected_at: datetime
    reachable: bool

    # Métricas comunes (opcionales; None si el equipo no las reporta)
    latency_ms: float | None
    cpu_percent: float | None
    ram_percent: float | None
    uptime_seconds: int | None

    # Interfaces de red
    interfaces: list[InterfaceMetrics]

    # PON/GPON (solo OLT)
    onus: list[ONUMetrics] | None

    # Radio (Ubiquiti, Mimosa)
    signal_dbm: float | None
    noise_floor_dbm: float | None
    tx_capacity_mbps: float | None
    rx_capacity_mbps: float | None

    # Datos raw para debugging (no se escribe a DB, solo logs)
    raw: dict | None = None
```

Este diseño garantiza que agregar un nuevo tipo de equipo (ej. SNMP genérico, Cambium) solo requiere: 1) una nueva clase collector, 2) un nuevo entry en el registry. Cero cambios en el Worker, la API, o el dashboard.

---

## Data Flow — Cómo se mueve la información

### Flujo principal: Poll → Store → Stream

```
1. SCHEDULER (cada 30s)
   └─► Celery Beat enqueue task `poll_device` por cada device activo en DB
       Payload: { device_id, device_type, connection_params }

2. WORKER (concurrente)
   ├─► Recibe task de Redis queue
   ├─► Selecciona collector via registry
   ├─► collector.health_check() — si falla, marca DOWN, salta collect()
   ├─► collector.collect() — conecta, extrae, normaliza → DeviceMetrics
   ├─► Escribe métricas a PostgreSQL (tabla metrics, particionada por tiempo)
   ├─► Actualiza last_seen + status en tabla devices
   ├─► Publica en Redis pub/sub canal `metrics:{device_id}` el DeviceMetrics serializado
   └─► Evalúa Alert Engine (ver flujo de alertas)

3. WEB SERVICE (siempre corriendo)
   ├─► Suscribe a Redis pub/sub `metrics:*` al arrancar
   ├─► Cuando llega publicación → reenvía al WebSocket/SSE del browser correspondiente
   └─► REST queries van directamente a PostgreSQL

4. BROWSER (dashboard)
   ├─► Al cargar: GET /api/devices → estado actual desde Redis cache (fast)
   ├─► Abre conexión SSE o WebSocket a /api/stream
   └─► Recibe actualizaciones push en tiempo real conforme llegan los polls
```

### Flujo de alertas

```
Alert Engine (dentro del Worker, post-collect):
├─► Lee umbrales desde DB (o Redis cache de umbrales)
├─► Compara DeviceMetrics contra umbrales (cpu > 90%, signal < -85dBm, etc.)
├─► Si umbral superado:
│   ├─► INSERT alert en tabla alerts (si no existe alerta activa para ese device+tipo)
│   ├─► INSERT incident en tabla incidents
│   └─► POST a Telegram Bot API (async, no bloquea el ciclo de polling)
└─► Si dispositivo RECOVERY (volvió UP):
    ├─► UPDATE alert → resolved_at
    └─► Notificación de recuperación a Telegram
```

### Flujo de lectura del dashboard (latencia)

```
GET /api/devices/status:
├─► Intenta Redis cache primero (TTL 60s) → respuesta < 5ms
└─► Fallback: SELECT last metrics desde PostgreSQL → ~20-50ms

GET /api/devices/{id}/history?range=24h:
└─► PostgreSQL query con index en (device_id, collected_at DESC)
    Para 500 equipos × 24h × poll cada 30s = ~1.4M rows/día → manejable con BRIN index
```

---

## Storage Design

### PostgreSQL — Esquema clave

```sql
-- Inventario de equipos
CREATE TABLE devices (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name        TEXT NOT NULL,
    ip          INET NOT NULL,
    type        TEXT NOT NULL,  -- 'mikrotik','vsol_olt','ubiquiti','mimosa'
    location    TEXT,
    status      TEXT DEFAULT 'unknown',  -- 'up','down','degraded','unknown'
    last_seen   TIMESTAMPTZ,
    config      JSONB,  -- credenciales encriptadas, parámetros de conexión
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- Métricas históricas — particionada por mes
CREATE TABLE metrics (
    id          BIGSERIAL,
    device_id   UUID NOT NULL REFERENCES devices(id),
    collected_at TIMESTAMPTZ NOT NULL,
    reachable   BOOLEAN NOT NULL,
    latency_ms  REAL,
    cpu_percent REAL,
    ram_percent REAL,
    signal_dbm  REAL,
    tx_mbps     REAL,
    rx_mbps     REAL,
    extra       JSONB  -- campos específicos del tipo de equipo
) PARTITION BY RANGE (collected_at);

-- Index primario para queries de historial
CREATE INDEX ON metrics (device_id, collected_at DESC);

-- Alertas activas e historial
CREATE TABLE alerts (
    id          BIGSERIAL PRIMARY KEY,
    device_id   UUID NOT NULL REFERENCES devices(id),
    alert_type  TEXT NOT NULL,  -- 'down','high_cpu','low_signal', etc.
    severity    TEXT NOT NULL,  -- 'critical','warning','info'
    triggered_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    resolved_at  TIMESTAMPTZ,
    message     TEXT
);

-- Incidentes (agrupación de alerts por outage)
CREATE TABLE incidents (
    id          BIGSERIAL PRIMARY KEY,
    device_id   UUID NOT NULL REFERENCES devices(id),
    started_at  TIMESTAMPTZ NOT NULL,
    ended_at    TIMESTAMPTZ,
    duration_seconds INT GENERATED ALWAYS AS (
        EXTRACT(EPOCH FROM (COALESCE(ended_at, NOW()) - started_at))
    ) STORED,
    root_alert_id BIGINT REFERENCES alerts(id),
    notes       TEXT
);

-- ONUs GPON (relativamente estáticas; se actualizan con cada OLT poll)
CREATE TABLE onus (
    id          BIGSERIAL PRIMARY KEY,
    olt_id      UUID NOT NULL REFERENCES devices(id),
    onu_index   TEXT NOT NULL,  -- identificador interno de la OLT
    serial      TEXT,
    status      TEXT,
    rx_power_dbm REAL,
    tx_power_dbm REAL,
    client_name TEXT,
    last_updated TIMESTAMPTZ,
    UNIQUE (olt_id, onu_index)
);
```

**Por qué PostgreSQL puro y no TimescaleDB:**
- Railway managed Postgres no garantiza TimescaleDB en todos los tiers
- 500 equipos × 2 polls/min × 60 min × 24h = ~1.44M rows/día — PostgreSQL estándar con particionamiento por mes + BRIN index es completamente suficiente a esta escala
- TimescaleDB añade valor real a partir de ~10M+ rows/día o cuando se necesita continuous aggregates complejos
- Menos dependencias = menos superficie de falla

**Retención:** Particionar por mes permite `DROP TABLE metrics_2025_01` para retención sin overhead de DELETE masivos.

---

## Real-time: WebSockets vs SSE

**Decisión: SSE (Server-Sent Events) para el dashboard principal.**

| Criterio | WebSocket | SSE |
|----------|-----------|-----|
| Dirección | Bidireccional | Unidireccional (server → client) |
| Complejidad server | Mayor (estado de conexión) | Menor (HTTP long-lived) |
| Reconexión automática | Manual | Nativa en browser |
| Compatibilidad | Universal | Universal (todos los browsers modernos) |
| Caso de uso NOC | Overkill para v1 | Perfecto — solo necesitamos push de métricas |
| Railway support | Requiere sticky sessions | Funciona sobre HTTP/2 estándar |

El dashboard de un NOC es primariamente lectura. El técnico no envía datos al servidor en tiempo real — solo recibe actualizaciones. SSE es la herramienta correcta.

**Implementación con FastAPI:**
```python
@app.get("/api/stream")
async def stream_metrics(request: Request):
    async def event_generator():
        pubsub = redis.pubsub()
        await pubsub.psubscribe("metrics:*")
        async for message in pubsub.listen():
            if await request.is_disconnected():
                break
            if message["type"] == "pmessage":
                yield f"data: {message['data']}\n\n"
    return StreamingResponse(event_generator(), media_type="text/event-stream")
```

**WebSocket para v2:** Si se agrega control remoto (reboot, config push), entonces WebSocket es justificado. Dejar la puerta abierta en el diseño pero no implementar en v1.

---

## Concurrencia del Worker — Dimensionamiento

### El problema: 500 equipos, poll cada 30s

- 500 tasks/30s = 16.7 tasks/segundo en promedio
- Cada poll toma entre 0.5s (ping) y 5s (SSH a OLT con muchas ONUs)
- Concurrencia necesaria: al menos 50-100 workers simultáneos para no atrasarse

### Solución: Celery con gevent o eventlet pool

```
celery worker --concurrency=100 --pool=gevent
```

Con `gevent`, un solo proceso Python puede manejar 100+ conexiones de red concurrentes eficientemente (I/O bound, no CPU bound). Esto corre perfectamente en Railway con un solo container de worker.

**Alternativa para SSH/Telnet (VSOL OLT):** `asyncssh` es async nativo. Los collectors de SSH deben ser implementados como coroutines y ejecutados en Celery con pool `gevent` o en una task pool asyncio separada dentro del worker.

**No usar threading pool para esto:** GIL de Python hace threading ineficiente para I/O intensivo. Gevent + monkeypatching o asyncio son las opciones correctas.

### Configuración de Celery Beat (scheduler)

```python
CELERY_BEAT_SCHEDULE = {
    "poll-all-devices": {
        "task": "worker.tasks.enqueue_device_polls",
        "schedule": 30.0,  # cada 30 segundos
    },
    "cleanup-old-metrics": {
        "task": "worker.tasks.cleanup_metrics",
        "schedule": crontab(hour=3, minute=0),  # diario a las 3am
    },
}

# La task enqueue_device_polls hace:
# SELECT id, type, ip, config FROM devices WHERE active=true
# Para cada device: apply_async(poll_device, args=[device_id], queue='polling')
```

### Prioridades de queue

```
Queues:
- polling    (prioridad normal — bulk de todos los devices)
- alerts     (prioridad alta — procesamiento de alerts y Telegram)
- maintenance (prioridad baja — cleanup, agregaciones)
```

---

## Anti-Patterns a Evitar

### Anti-Pattern 1: Polling desde el frontend (browser)
**Qué pasa:** Cada técnico hace polling directo a los equipos desde el browser.
**Por qué es malo:** Los equipos están en red privada — el browser no puede alcanzarlos. Incluso si pudiera, 500 equipos × 60s = carga imposible.
**En cambio:** Todo el polling ocurre en el worker server-side. El browser solo recibe actualizaciones vía SSE.

### Anti-Pattern 2: Un collector "universal" que soporta todos los protocolos
**Qué pasa:** Un solo módulo con if/elif gigante para cada tipo de equipo.
**Por qué es malo:** No escala cuando hay que agregar Cambium, SNMP, etc. Tests imposibles de mantener. Bugs en un equipo afectan todos.
**En cambio:** Protocol Adapter Pattern con registry. Cada collector es independiente.

### Anti-Pattern 3: Guardar credenciales en texto plano en la DB
**Qué pasa:** `INSERT INTO devices (config) VALUES ('{"password": "admin123"}')`
**Por qué es malo:** Credenciales de 500 equipos de producción en texto plano.
**En cambio:** Encriptar el campo `config` de `devices` con `cryptography.fernet` o similar. Clave de encriptación en variable de entorno Railway, nunca en código o DB.

### Anti-Pattern 4: Timeout sin límite en collectors SSH/Telnet
**Qué pasa:** OLT VSOL que no responde bloquea un worker indefinidamente.
**Por qué es malo:** Con 100 workers y 50 OLTs colgadas, se agotan todos los workers.
**En cambio:** Timeout explícito en cada collector (SSH: 10s connect, 30s max operación). Circuit breaker: si un device falla 3 veces consecutivas, skip por 5 minutos.

### Anti-Pattern 5: Escribir cada métrica como una fila por valor individual
**Qué pasa:** Una fila para CPU, otra para RAM, otra para latency, etc.
**Por qué es malo:** Wide-row approach — queries de "dame todas las métricas de este device" requieren N joins o N queries.
**En cambio:** Una fila por poll por device, con columnas para cada métrica. `extra JSONB` para campos específicos del tipo. Una query = todo el snapshot.

---

## Scalability Considerations

| Concern | A 500 equipos (v1) | A 2000 equipos (v2) | A 10K equipos |
|---------|-------------------|---------------------|---------------|
| Polling concurrency | Celery + gevent 100 workers | Aumentar concurrency a 300 | Múltiples worker instances |
| DB write throughput | ~50 rows/s — trivial para PG | ~200 rows/s — aún manejable | Sharding o TimescaleDB real |
| SSE connections | 1 técnico = 1 conexión | Multi-usuario: Redis pub/sub escala bien | Load balancer con sticky sessions |
| Poll interval | 30s cómodo | 30s aún factible | Algunos equipos a 60s, críticos a 15s |
| Railway costs | 2 services + managed Redis + PG | 3-4 services | Migrar a VPS o Kubernetes |

---

## Build Order — Dependencias entre Componentes

El orden de construcción sigue las dependencias de datos y de testing:

```
FASE 1: Foundation (prerequisito de todo lo demás)
├─► Database schema (devices, metrics, alerts, incidents, onus)
├─► Device inventory CRUD (API + DB)
└─► Auth básico (JWT, un usuario hardcoded para v1)

FASE 2: Collector Layer (el núcleo del valor)
├─► BaseCollector interface + DeviceMetrics model
├─► MikrotikCollector (RouterOS API — el más documentado, empieza aquí)
├─► Tests con un Mikrotik real de dev
└─► Framework de tests mockeables para los demás collectors

FASE 3: Worker Pipeline (conecta collectors con storage)
├─► Celery setup + Redis
├─► Task poll_device básico (health_check + collect + write)
├─► Celery Beat scheduler (30s interval)
└─► Verificar que métricas aparecen en DB

FASE 4: Collectors restantes
├─► VSOLCollector (SSH/Telnet + parseo CLI — el más complejo)
├─► UbiquitiCollector (UISP API preferida; SSH fallback)
└─► MimosaCollector (REST API — el más simple)

FASE 5: Alert Engine
├─► Threshold evaluation (post-poll hook)
├─► Alert deduplication (no enviar 500 Telegrams en 30s)
└─► Telegram Bot integration

FASE 6: Web API + SSE
├─► REST endpoints (/devices, /metrics, /alerts, /incidents)
├─► Redis pub/sub subscription en FastAPI startup
└─► SSE endpoint /api/stream

FASE 7: Dashboard Frontend
├─► Device grid (estado UP/DOWN/degraded)
├─► SSE client (auto-reconnect)
└─► Detail view por device (historial 24h)

FASE 8: Production
├─► Credential encryption (Fernet)
├─► Circuit breaker por device
└─► Deploy Railway con variables de entorno
```

**Por qué este orden:**
- Fases 1-3 permiten tener datos reales en DB antes de construir el frontend
- Fase 2 antes que Fase 3: los collectors deben ser testeables de forma aislada (sin Celery)
- Fase 5 (alertas) después de Fase 3: necesita datos para validar umbrales
- Fase 7 al final: el frontend es el que muestra valor pero tiene todas las dependencias; construirlo sobre datos reales es mucho más eficiente que mocks

---

## Technology Choices Implication

| Tecnología | Decisión | Impacto en arquitectura |
|------------|----------|------------------------|
| Python + FastAPI | Web service | Async nativo; compatible con asyncssh; mismo lenguaje que el worker |
| Celery + Redis | Task queue | Probado en producción; gevent pool para I/O concurrente; Beat incluido |
| PostgreSQL | Storage | Sin dependencia de TimescaleDB; particionamiento nativo en PG 14+ |
| SSE | Real-time push | Más simple que WebSocket; browser reconecta automáticamente |
| asyncssh | SSH/Telnet | Async nativo; crítico para no bloquear el event loop en OLTs VSOL |
| routeros-api | Mikrotik | Librería Python para RouterOS API v2; async compatible |
| Redis pub/sub | SSE bridge | Desacopla el worker (que escribe) del web server (que sirve SSE) sin estado compartido |

---

## Sources

- Patrones establecidos en LibreNMS (https://github.com/librenms/librenms) — arquitectura de polling y alert deduplication
- Zabbix architecture docs — scheduler/poller/trapper separation
- Celery documentation — gevent pool, beat scheduler, priority queues
- FastAPI SSE patterns — StreamingResponse + Redis pub/sub
- PostgreSQL partitioning docs — PARTITION BY RANGE para time-series
- asyncssh documentation — SSH async en Python
- Confidence: HIGH para patrones de polling y storage (maduros y documentados); MEDIUM para Railway-specific constraints (verificar gevent en el container de Railway al momento de deploy)
