# Phase 1: Infrastructure — Research

**Researched:** 2026-04-25
**Domain:** Railway PaaS deployment, WireGuard VPN, PostgreSQL schema, Fernet encryption, Celery multi-service
**Confidence:** HIGH (core stack), MEDIUM (Railway + WireGuard), LOW (Railway NET_ADMIN)

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**VPN / Conectividad Railway → Red ISP**
- WireGuard con el Mikrotik core (IP pública) como servidor
- El Mikrotik actúa como servidor WireGuard; Railway corre el cliente
- Las keys WireGuard van en variables de entorno de Railway
- El worker Celery debe verificar conectividad VPN al arrancar

**RouterOS Version**
- RouterOS v7 es la versión principal
- `librouteros` soporta v6 y v7; mismos endpoints para Phase 3

**Estructura del Repositorio**
- Monorepo: `/backend` (FastAPI + Celery) + `/frontend` (React + Vite)
- `docker-compose.yml` solo referencia local, NO es el deploy target

**Estrategia de Deploy**
- Railway directamente desde el inicio — sin Docker Compose local
- Railway services: `web`, `worker`, `beat`, `db` (PostgreSQL managed), `redis` (Railway managed)

**Base de Datos**
- PostgreSQL Railway managed desde el inicio — nunca SQLite
- Schema inicial: `devices`, `device_credentials`, `metrics`, `alerts`, `incidents`, `onus`
- Migraciones con Alembic desde el día 1
- Retención: métricas e incidentes > 30 días se limpian con Celery beat

**Gestión de Credenciales**
- Credenciales de infraestructura → variables de entorno Railway (nunca en código)
- Credenciales de equipos de red → PostgreSQL encriptadas con Fernet (`FERNET_KEY` = env var)

### Claude's Discretion
- Schema exacto de las tablas (columnas, tipos, índices)
- Nombre de columnas — seguir snake_case Python estándar
- Versión exacta de librerías Python — elegir las más recientes estables
- Estructura interna de carpetas dentro de `/backend/app/`

### Deferred Ideas (OUT OF SCOPE)
- Frontend (Phase 2+)
- Lógica de polling (Phase 2)
- Collectors de equipos (Phase 3+)
- Alertas Telegram (Phase 3)
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| INFRA-01 | Establecer túnel VPN WireGuard desde Railway a la red privada del ISP | Sección WireGuard: NET_ADMIN no disponible en Railway → Tailscale userspace es el camino viable |
| INFRA-02 | PostgreSQL Railway managed configurada desde el inicio — sin almacenamiento local efímero | Sección Standard Stack: schema + Alembic async config documentados |
| INFRA-03 | Variables de entorno para todas las credenciales (ninguna hardcodeada) | Sección Architecture Patterns: env var mapping + Fernet key rotation |
| DEPLOY-01 | La aplicación corre en Railway con servicios web (FastAPI) y worker (Celery) | Sección railway.toml: configuración multi-servicio desde monorepo documentada |
| DEPLOY-02 | Dominio personalizado de BEEPYRED apunta a Railway | Fuera de alcance técnico de este research — es configuración DNS/Railway dashboard |
| DEPLOY-03 | Credenciales de equipos encriptadas en base de datos, no en texto plano | Sección Standard Stack: Fernet encryption pattern con cryptography 47.x documentado |
</phase_requirements>

---

## Summary

Phase 1 establece la base de ejecución del NOC: conectividad VPN desde Railway a la red privada del ISP, base de datos PostgreSQL persistente con schema inicial, y manejo seguro de credenciales. El hallazgo crítico de esta investigación es que **Railway no permite NET_ADMIN ni modo privilegiado** para contenedores Docker, lo que hace imposible WireGuard kernel-mode. La alternativa viable es **Tailscale en modo userspace** (`TS_USERSPACE=1`), que funciona sin capacidades privilegiadas pero requiere que la aplicación configure el proxy explícitamente. La segunda alternativa es correr el worker Celery en hardware local del ISP y solo el API web en Railway, separando los planos de control y datos.

Para la base de datos, el stack verificado es FastAPI 0.136 + SQLAlchemy 2.0 + Alembic 1.18 + asyncpg 0.31, con Alembic inicializado en modo async (`alembic init -t async`). El schema inicial debe incluir las seis tablas requeridas con índices apropiados para los patrones de acceso del NOC. Para credenciales de equipos, `cryptography` 47.x con Fernet es la elección estándar — la librería está activamente mantenida y disponible en PyPI.

La configuración de railway.toml para múltiples servicios desde un monorepo se hace con `startCommand` diferente por servicio en archivos `railway.toml` individuales dentro del directorio de cada servicio o a través del dashboard de Railway. Celery beat DEBE correr como servicio separado del worker (la opción `-B` embebida está explícitamente desaconsejada para producción por la documentación oficial de Celery).

**Primary recommendation:** Usar Tailscale userspace mode en el worker Celery como solución VPN en Railway. Si la conectividad a equipos es el cuello de botella, mover el worker a hardware local del ISP y mantener solo el API en Railway.

---

## CRITICAL FINDING: Railway no soporta NET_ADMIN / WireGuard kernel

Este es el hallazgo más importante de la investigación. Impacta directamente INFRA-01.

**Lo que se intentó investigar:** ¿Railway permite NET_ADMIN capability para WireGuard kernel module?

**Resultado verificado:** Railway **prohíbe** explícitamente:
- Contenedores privilegiados
- La capability `NET_ADMIN` o `SYS_MODULE`
- Docker-in-Docker
- Cualquier acceso al runtime del contenedor

Fuente: Railway Help Station feedback thread "Allow services to be run in privileged mode" confirmado por empleado oficial de Railway. [VERIFIED: station.railway.com]

**Consecuencia directa:** WireGuard kernel-mode (que requiere `--cap-add=NET_ADMIN` y acceso a `/dev/net/tun`) **no es posible en Railway**. `boringtun` y `wireguard-go` en modo userspace tampoco, porque aun en userspace necesitan `NET_ADMIN` para crear la interfaz virtual `tun0`.

**Opciones disponibles para INFRA-01:**

| Opción | Viabilidad en Railway | Complejidad | Recomendación |
|--------|----------------------|-------------|---------------|
| WireGuard kernel-mode | IMPOSIBLE | — | NO |
| boringtun / wireguard-go userspace | IMPOSIBLE (también necesita NET_ADMIN) | — | NO |
| **Tailscale userspace (TS_USERSPACE=1)** | **VIABLE** | Media | **Sí para worker** |
| Headscale (self-hosted coordinator) | Viable pero más complejo | Alta | Solo si Tailscale SaaS inaceptable |
| Worker Celery on-premises en red ISP | Siempre viable | Media | Fallback definitivo |

---

## Standard Stack

### Core (Phase 1 specific)

Versiones verificadas contra PyPI registry el 2026-04-25:

| Library | Version Verified | Purpose | Source |
|---------|-----------------|---------|--------|
| FastAPI | 0.136.1 | API framework + Celery app | [VERIFIED: pip index] |
| Uvicorn | 0.46.0 | ASGI server para FastAPI | [VERIFIED: pip index] |
| SQLAlchemy | 2.0.49 | ORM async para PostgreSQL | [VERIFIED: pip index] |
| asyncpg | 0.31.0 | Driver PostgreSQL async | [VERIFIED: pip index] |
| Alembic | 1.18.4 | Migraciones de DB | [VERIFIED: pip index] |
| Celery | 5.6.3 | Task queue (worker + beat) | [VERIFIED: pip index] |
| redis (Python client) | 7.4.0 | Cliente Redis para Celery broker | [VERIFIED: pip index] |
| pydantic | 2.13.3 | Validación de datos y settings | [VERIFIED: pip index] |
| cryptography | 47.0.0 | Fernet encryption para credenciales | [VERIFIED: pypi.org] |
| python-dotenv | 1.2.2 | Carga .env en desarrollo local | [VERIFIED: pip index] |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| gunicorn | 22.x | Process manager para uvicorn | Solo en producción Railway (web service) |
| pydantic-settings | 2.x | Settings management desde env vars | Siempre — mejor que os.environ directo |
| httpx | 0.28.x | HTTP cliente para health checks | Tests y verificación de VPN |

### VPN — Tailscale Userspace en Railway

| Component | Version | Purpose | Notes |
|-----------|---------|---------|-------|
| tailscale/tailscale | latest | VPN client en contenedor worker | TS_USERSPACE=1 para no requerir NET_ADMIN |
| Tailscale SaaS | — | Coordinator/relay | Requiere cuenta Tailscale (gratis para proyectos pequeños) |

**Alternativa:** Si Tailscale SaaS no es aceptable: mover worker Celery a on-premises (Raspberry Pi / servidor en red ISP).

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Tailscale | WireGuard directo | WireGuard kernel mode imposible en Railway; boringtun también requiere NET_ADMIN |
| Tailscale | Worker on-premises | On-premises = más control y rendimiento de red, pero requiere hardware adicional y mantenimiento |
| asyncpg | psycopg3 | psycopg3 tiene soporte async nativo; asyncpg sigue siendo más rápido en benchmarks; ambos son válidos |
| Fernet (cryptography) | pgcrypto | pgcrypto cifra en PostgreSQL (más complejo); Fernet en Python es más portable y testeable |
| SQLAlchemy 2.0 | Tortoise ORM | SQLAlchemy tiene mucho más soporte de comunidad y Alembic como migration tool nativo |

### Installation

```bash
# Backend - Phase 1 dependencies
pip install \
  "fastapi==0.136.1" \
  "uvicorn[standard]==0.46.0" \
  "gunicorn==22.*" \
  "pydantic==2.13.3" \
  "pydantic-settings==2.*" \
  "sqlalchemy[asyncio]==2.0.49" \
  "asyncpg==0.31.0" \
  "alembic==1.18.4" \
  "celery[redis]==5.6.3" \
  "redis==7.4.0" \
  "cryptography==47.0.0" \
  "python-dotenv==1.2.2" \
  "httpx==0.28.*"
```

---

## Architecture Patterns

### Recommended Project Structure

```
beepyred-noc/
├── backend/
│   ├── app/
│   │   ├── api/             # FastAPI routers (Phase 2+)
│   │   ├── core/
│   │   │   ├── config.py    # pydantic-settings Settings class
│   │   │   ├── database.py  # async engine + session factory
│   │   │   └── security.py  # Fernet encrypt/decrypt helpers
│   │   ├── models/          # SQLAlchemy declarative models
│   │   │   ├── base.py      # Base class + metadata
│   │   │   ├── device.py
│   │   │   ├── metric.py
│   │   │   ├── alert.py
│   │   │   ├── incident.py
│   │   │   └── onu.py
│   │   ├── tasks/           # Celery tasks (Phase 2+)
│   │   │   └── maintenance.py  # cleanup task (Phase 1: stub)
│   │   └── main.py          # FastAPI app factory
│   ├── alembic/
│   │   ├── env.py           # async Alembic config
│   │   ├── script.py.mako
│   │   └── versions/
│   │       └── 001_initial_schema.py
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── alembic.ini
│   └── railway.toml         # Para web service
├── frontend/                # Phase 2+
├── .env.example             # Template — nunca .env real en git
└── .planning/
```

### Pattern 1: Alembic Async Configuration

Alembic con asyncpg requiere la template async y configuración especial en env.py. El engine síncrono clásico no funciona con asyncpg.

```python
# alembic/env.py — async mode
# Source: Alembic oficial docs + https://berkkaraal.com/blog/2024/09/19/...

import asyncio
from logging.config import fileConfig
from sqlalchemy.ext.asyncio import async_engine_from_config
from sqlalchemy import pool
from alembic import context
from app.models.base import Base
from app.core.config import settings

config = context.config
fileConfig(config.config_file_name)
target_metadata = Base.metadata

# Railway PostgreSQL URL viene de env var DATABASE_URL
# asyncpg requiere postgresql+asyncpg:// prefix
config.set_main_option(
    "sqlalchemy.url",
    settings.DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://")
)


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(
            lambda sync_conn: context.configure(
                connection=sync_conn, target_metadata=target_metadata
            )
        )
        async with connection.begin():
            await connection.run_sync(lambda _: context.run_migrations())
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
```

**Inicializar con template async:**
```bash
# Desde /backend/
alembic init -t async alembic
```

### Pattern 2: Fernet Encryption para Device Credentials

```python
# app/core/security.py
# Source: cryptography.io/en/latest/fernet/ [CITED]

from cryptography.fernet import Fernet
from app.core.config import settings

def get_fernet() -> Fernet:
    """Crea instancia Fernet desde FERNET_KEY env var."""
    return Fernet(settings.FERNET_KEY.encode())


def encrypt_credential(plaintext: str) -> str:
    """Encripta credencial de equipo para almacenar en DB."""
    f = get_fernet()
    return f.encrypt(plaintext.encode()).decode()


def decrypt_credential(ciphertext: str) -> str:
    """Desencripta credencial de equipo recuperada de DB."""
    f = get_fernet()
    return f.decrypt(ciphertext.encode()).decode()


# Generar FERNET_KEY una sola vez en Railway:
# python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

**Regla de seguridad:** La `FERNET_KEY` es una variable de entorno Railway. Si se pierde, las credenciales almacenadas no se pueden recuperar. Documentar en runbook operativo.

### Pattern 3: pydantic-settings para Configuración

```python
# app/core/config.py
# Source: docs.pydantic.dev/latest/concepts/pydantic_settings/ [ASSUMED - pattern estándar]

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # Database — Railway provee DATABASE_URL automáticamente
    DATABASE_URL: str

    # Redis — Railway provee REDIS_URL automáticamente
    REDIS_URL: str

    # Seguridad
    SECRET_KEY: str
    FERNET_KEY: str

    # Telegram (Phase 3 — incluir ahora para no redeployar)
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_CHAT_ID: str = ""

    # WireGuard / Tailscale
    TAILSCALE_AUTH_KEY: str = ""

    # Polling config (Phase 2)
    POLL_INTERVAL_SECONDS: int = 60
    MAX_CONCURRENT_CONNECTIONS: int = 50

    # Railway auto-provides PORT
    PORT: int = 8000


settings = Settings()
```

### Pattern 4: Railway Multi-Service desde Monorepo

Railway no tiene un `railway.toml` "raíz" que defina múltiples servicios. Cada servicio Railway apunta a un `railway.toml` específico (o se configura en el dashboard).

**Approach recomendado:** Un solo `railway.toml` en `/backend/` con el Dockerfile compartido. El `startCommand` se diferencia por servicio en el **dashboard de Railway** (campo "Start Command" en cada servicio). Esto evita mantener múltiples archivos de config.

```toml
# /backend/railway.toml  — aplica al servicio web por defecto
[build]
builder = "DOCKERFILE"
dockerfilePath = "Dockerfile"

[deploy]
startCommand = "gunicorn app.main:app -w 2 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:$PORT"
healthcheckPath = "/health"
healthcheckTimeout = 30
restartPolicyType = "ON_FAILURE"
restartPolicyMaxRetries = 3
```

**Start commands por servicio (configurar en Railway dashboard):**

| Service | Start Command |
|---------|--------------|
| `web` | `gunicorn app.main:app -w 2 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:$PORT` |
| `worker` | `celery -A app.celery_app worker --loglevel=info --concurrency=4` |
| `beat` | `celery -A app.celery_app beat --loglevel=info --scheduler celery.beat:PersistentScheduler` |

**Advertencia:** Celery beat DEBE ser un servicio separado. La opción `-B` (beat embebido en worker) está explícitamente desaconsejada en la documentación oficial de Celery para producción porque produce tareas duplicadas si hay más de una instancia del worker. [VERIFIED: docs.celeryq.dev]

### Pattern 5: Tailscale Userspace en Dockerfile del Worker

Tailscale en modo userspace (`TS_USERSPACE=1`) no requiere NET_ADMIN. El tradeoff es que el networking VPN se expone como SOCKS5/HTTP proxy — la aplicación debe configurar sus llamadas de red para pasar por el proxy.

```dockerfile
# Dockerfile — stage base compartido entre web y worker
FROM python:3.12-slim AS base
WORKDIR /app

# Instalar dependencias del sistema
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Stage para worker con Tailscale
FROM base AS worker
# Instalar tailscale CLI
RUN curl -fsSL https://tailscale.com/install.sh | sh

# Script de arranque: inicializar Tailscale y luego iniciar Celery
COPY scripts/start-worker.sh /start-worker.sh
RUN chmod +x /start-worker.sh
CMD ["/start-worker.sh"]
```

```bash
#!/bin/bash
# scripts/start-worker.sh
# Source: tailscale.com/docs/features/containers/docker [CITED]

# Iniciar tailscaled en background con userspace networking
tailscaled --tun=userspace-networking --socks5-server=localhost:1055 &

# Esperar a que tailscaled esté listo
sleep 2

# Autenticar con Tailscale usando auth key
tailscale up --authkey="${TAILSCALE_AUTH_KEY}" --hostname="beepyred-noc-worker"

echo "Tailscale conectado. Iniciando Celery worker..."

# Exportar proxy para que las librerías Python lo usen
export ALL_PROXY=socks5://localhost:1055

# Iniciar Celery worker
exec celery -A app.celery_app worker --loglevel=info --concurrency=4
```

**Limitación crítica de userspace mode:** El proxy SOCKS5 solo funciona si las librerías Python usadas para conectarse a equipos de red (librouteros, asyncssh, aiohttp) tienen soporte para SOCKS5 proxy. Verificar esto antes de implementar Phase 2.

- `aiohttp`: soporta proxies via `aiohttp-socks` [ASSUMED - verificar]
- `asyncssh`: soporte de proxy es limitado [ASSUMED - verificar antes de Phase 3]
- `librouteros`: no tiene soporte nativo de SOCKS5 proxy [ASSUMED - riesgo]

**Si las librerías no soportan SOCKS5:** El fallback es mover el worker a on-premises.

### Pattern 6: PostgreSQL Schema Inicial

```python
# app/models/device.py
# Source: diseño propio basado en requirements INFRA-02 [ASSUMED - esquema no existe aún]

import enum
from datetime import datetime
from sqlalchemy import String, Integer, Boolean, DateTime, Text, Enum
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base


class DeviceType(enum.Enum):
    MIKROTIK = "mikrotik"
    OLT_VSOL_GPON = "olt_vsol_gpon"
    OLT_VSOL_EPON = "olt_vsol_epon"
    ONU = "onu"
    UBIQUITI = "ubiquiti"
    MIMOSA = "mimosa"
    OTHER = "other"


class DeviceStatus(enum.Enum):
    UP = "up"
    DOWN = "down"
    WARNING = "warning"
    UNKNOWN = "unknown"


class Device(Base):
    __tablename__ = "devices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    ip_address: Mapped[str] = mapped_column(String(45), nullable=False)  # IPv4/IPv6
    device_type: Mapped[DeviceType] = mapped_column(Enum(DeviceType), nullable=False)
    site: Mapped[str | None] = mapped_column(String(255), nullable=True)  # Torre Norte, Nodo Centro
    status: Mapped[DeviceStatus] = mapped_column(
        Enum(DeviceStatus), default=DeviceStatus.UNKNOWN, nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )
    # Para ONU: FK a OLT padre
    parent_device_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pon_port: Mapped[str | None] = mapped_column(String(50), nullable=True)  # Para ONUs
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
```

```python
# app/models/device_credential.py
# Credenciales de equipos encriptadas con Fernet (DEPLOY-03)

from sqlalchemy import String, Integer, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base


class DeviceCredential(Base):
    __tablename__ = "device_credentials"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_id: Mapped[int] = mapped_column(Integer, ForeignKey("devices.id", ondelete="CASCADE"), nullable=False)
    credential_type: Mapped[str] = mapped_column(String(50), nullable=False)  # "ssh", "api", "snmp", "http"
    username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # encrypted_password y encrypted_api_key almacenan texto cifrado con Fernet
    encrypted_password: Mapped[str | None] = mapped_column(Text, nullable=True)
    encrypted_api_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    port: Mapped[int | None] = mapped_column(Integer, nullable=True)
```

```python
# app/models/metric.py
# Para TimescaleDB: created_at es la dimensión temporal del hypertable

from datetime import datetime
from decimal import Decimal
from sqlalchemy import Integer, ForeignKey, DateTime, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base


class Metric(Base):
    __tablename__ = "metrics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_id: Mapped[int] = mapped_column(Integer, ForeignKey("devices.id", ondelete="CASCADE"), nullable=False)
    metric_name: Mapped[str] = mapped_column(String(100), nullable=False)  # "cpu_pct", "ram_pct", "rx_bps", "signal_dbm"
    value: Mapped[Decimal] = mapped_column(Numeric(precision=12, scale=4), nullable=False)
    unit: Mapped[str | None] = mapped_column(String(20), nullable=True)  # "%", "bps", "dBm"
    interface: Mapped[str | None] = mapped_column(String(100), nullable=True)  # Para métricas por interfaz
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )
    # TimescaleDB hypertable partition key = recorded_at
```

```python
# app/models/incident.py

from datetime import datetime
from sqlalchemy import Integer, ForeignKey, DateTime, Text, Interval
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base


class Incident(Base):
    __tablename__ = "incidents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_id: Mapped[int] = mapped_column(Integer, ForeignKey("devices.id", ondelete="CASCADE"), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)  # Calculado al cerrar incidente
    cause: Mapped[str | None] = mapped_column(Text, nullable=True)
    alert_sent: Mapped[bool] = mapped_column(default=False, nullable=False)
    recovery_alert_sent: Mapped[bool] = mapped_column(default=False, nullable=False)
```

```python
# app/models/alert.py — Configuración de umbrales de alerta

from sqlalchemy import Integer, ForeignKey, String, Numeric, Boolean
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base
from decimal import Decimal


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("devices.id", ondelete="CASCADE"), nullable=True
    )  # NULL = alerta global
    alert_type: Mapped[str] = mapped_column(String(100), nullable=False)  # "cpu_high", "signal_low", "down"
    threshold_value: Mapped[Decimal | None] = mapped_column(Numeric(precision=12, scale=4), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    consecutive_polls_required: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
```

```python
# app/models/onu.py — ONUs GPON/EPON (Phase 3/4, pero schema desde Phase 1)

from datetime import datetime
from decimal import Decimal
from sqlalchemy import Integer, ForeignKey, String, Numeric, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base


class ONU(Base):
    __tablename__ = "onus"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_id: Mapped[int] = mapped_column(Integer, ForeignKey("devices.id", ondelete="CASCADE"), nullable=False)
    olt_id: Mapped[int] = mapped_column(Integer, ForeignKey("devices.id", ondelete="SET NULL"), nullable=True)
    serial_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    pon_port: Mapped[str | None] = mapped_column(String(50), nullable=True)  # "0/1", "gpon0/1"
    signal_rx_dbm: Mapped[Decimal | None] = mapped_column(Numeric(precision=8, scale=4), nullable=True)
    signal_tx_dbm: Mapped[Decimal | None] = mapped_column(Numeric(precision=8, scale=4), nullable=True)
    onu_status: Mapped[str | None] = mapped_column(String(50), nullable=True)  # "ONLINE", "OFFLINE", "RANGING"
    last_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
```

**Índices críticos para el schema** (incluir en la migración inicial):
```sql
-- Para queries de dashboard (equipos por estado)
CREATE INDEX idx_devices_status ON devices(status);
CREATE INDEX idx_devices_site ON devices(site);
CREATE INDEX idx_devices_type ON devices(device_type);

-- Para queries de métricas (TimescaleDB hypertable)
CREATE INDEX idx_metrics_device_recorded ON metrics(device_id, recorded_at DESC);

-- Para incidentes activos (resolved_at IS NULL)
CREATE INDEX idx_incidents_active ON incidents(device_id, resolved_at) WHERE resolved_at IS NULL;
CREATE INDEX idx_incidents_started ON incidents(started_at DESC);

-- Para credenciales por equipo
CREATE UNIQUE INDEX idx_device_credentials_unique ON device_credentials(device_id, credential_type);
```

### Pattern 7: RouterOS v7 WireGuard — Configuración del Servidor Mikrotik

Aunque Railway no puede correr WireGuard kernel-mode, el Mikrotik debe estar configurado correctamente para cuando el cliente (Tailscale o worker on-premises) requiera acceso a la red privada. Si se usa Tailscale, el Mikrotik actúa como subnet router de Tailscale en vez de servidor WireGuard.

**Si se usa WireGuard puro (worker on-premises):**

```
# RouterOS v7 — Servidor WireGuard
# Source: help.mikrotik.com/docs/spaces/ROS/pages/69664792/WireGuard [CITED]

# 1. Crear interfaz WireGuard (genera keys automáticamente)
/interface wireguard
add listen-port=13231 name=wg-noc

# 2. Verificar keys generadas
/interface wireguard print

# 3. Asignar IP en la subred del túnel
/ip address
add address=10.99.0.1/24 interface=wg-noc

# 4. Agregar peer (Railway worker o servidor on-premises)
# public-key = clave pública del cliente (worker genera su par de claves)
/interface wireguard peers
add allowed-address=10.99.0.2/32 interface=wg-noc public-key="<CLIENT_PUBLIC_KEY>"

# 5. Firewall: permitir puerto UDP de WireGuard
/ip firewall filter
add action=accept chain=input comment="WireGuard NOC" dst-port=13231 protocol=udp place-before=1

# 6. Firewall: aceptar tráfico desde el túnel
/interface list member
add interface=wg-noc list=LAN
```

**Variables de entorno del worker con las keys:**
```bash
WG_PRIVATE_KEY=<private key del cliente — generada con wg genkey>
WG_SERVER_PUBLIC_KEY=<public key del Mikrotik — obtenida de /interface wireguard print>
WG_SERVER_ENDPOINT=<IP pública del Mikrotik>:13231
WG_CLIENT_IP=10.99.0.2/24
WG_ALLOWED_IPS=10.99.0.0/24,192.168.0.0/16  # Subnets del ISP
```

### Anti-Patterns to Avoid

- **NUNCA** usar `alembic init` (sin `-t async`) con asyncpg — el env.py síncrono no funciona con drivers async
- **NUNCA** correr Celery beat con flag `-B` en worker de producción — duplica tareas en multi-instance
- **NUNCA** almacenar `FERNET_KEY` en el código, Dockerfile, o repositorio
- **NUNCA** usar `DATABASE_URL` con prefix `postgresql://` para asyncpg — debe ser `postgresql+asyncpg://`
- **NUNCA** ejecutar `alembic upgrade head` como parte del CMD del Dockerfile — usar un entrypoint script separado o un Railway custom start command que haga la migración primero

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Credential encryption | Custom XOR/AES wrapper | `cryptography.fernet.Fernet` | Fernet maneja IV aleatorio, MAC authentication, y key rotation correctamente |
| Database migrations | Scripts SQL manuales | Alembic | Alembic trackea estado, permite rollback, auto-genera diferencias |
| Settings from env | `os.environ.get()` directo | `pydantic-settings BaseSettings` | Validación de tipos, valores por defecto, soporte .env, errores claros en startup |
| VPN client | WireGuard userspace manual | Tailscale | Tailscale resuelve NAT traversal, relay fallback, sin gestionar keys manualmente |
| Process manager | Shell scripts con restart | Gunicorn | Gunicorn maneja crashes, workers, señales SIGTERM correctamente |
| Async DB session | Conexiones asyncpg directas | SQLAlchemy async session | Connection pooling, transacciones, lazy loading — no re-inventar |
| Fernet key generation | Código propio de generación | `Fernet.generate_key()` | Genera 256-bit URL-safe base64 con suficiente entropía criptográfica |

**Key insight:** En este dominio, los problemas de seguridad (cifrado, manejo de keys, gestión de secretos) son exactamente donde las implementaciones caseras introducen vulnerabilidades sutiles. Usar herramientas auditadas.

---

## Common Pitfalls

### Pitfall 1: Railway destruye el filesystem en cada redeploy

**What goes wrong:** SQLite, archivos de config, logs en disco — todo se borra en cada deploy.

**Why it happens:** Railway usa contenedores inmutables. No hay persistencia de filesystem entre deployments.

**How to avoid:** PostgreSQL managed de Railway desde el día 1. NUNCA escribir estado a disco en el worker. El estado de polling (consecutive_failures, last_seen_at) vive en PostgreSQL, no en memoria ni en archivo.

**Warning signs:** Después de un deploy, `consecutive_failures` se resetea a 0 para todos los equipos, generando alertas falsas de "recuperación".

### Pitfall 2: asyncpg + Alembic con env.py síncrono

**What goes wrong:** `alembic upgrade head` falla con `MissingGreenlet` o `asyncpg.exceptions._base.InterfaceError`.

**Why it happens:** Alembic por defecto usa engines síncronos. asyncpg es asíncrono. Sin el template `-t async` y `async_engine_from_config`, la migración intenta correr código async en contexto síncrono.

**How to avoid:** `alembic init -t async alembic` desde el inicio. No migrar el env.py después.

**Warning signs:** Error `greenlet_spawn has not been called` en logs de migración.

### Pitfall 3: Celery beat duplica tareas si no es servicio independiente

**What goes wrong:** Al correr `celery worker -B`, si se escalan workers a 2+ instancias, cada instancia tiene su propio beat scheduler que dispara las tareas por su cuenta. Las tareas de limpieza de métricas corren N veces.

**Why it happens:** `-B` no tiene locking distribuido. La documentación de Celery 5.x lo describe explícitamente como "not recommended for production".

**How to avoid:** `beat` es un servicio Railway separado con `celery beat` (sin `worker`). Solo puede existir **una** instancia del beat service.

**Warning signs:** Las tareas periódicas aparecen en logs con timestamps duplicados segundos aparte.

### Pitfall 4: FERNET_KEY perdida = credenciales irrecuperables

**What goes wrong:** Se rota o se pierde la `FERNET_KEY`. Todas las credenciales de equipos en `device_credentials` no se pueden desencriptar. El sistema no puede conectarse a ningún equipo.

**Why it happens:** Fernet es cifrado simétrico. Sin la key original no hay recuperación.

**How to avoid:** Documentar la `FERNET_KEY` en un password manager (1Password, Bitwarden) desde el inicio. Antes de cambiar la key, re-encriptar todos los registros existentes con la nueva key.

**Warning signs:** Errores `cryptography.fernet.InvalidToken` al intentar conectar a equipos.

### Pitfall 5: Tailscale userspace no enruta tráfico de librerías sin soporte de proxy

**What goes wrong:** El worker tiene Tailscale en modo userspace con SOCKS5 proxy en `localhost:1055`. Se exporta `ALL_PROXY=socks5://localhost:1055`. Pero `librouteros` o `asyncssh` ignoran `ALL_PROXY` y conectan directamente — el tráfico no va por el túnel Tailscale y falla contra IPs privadas del ISP.

**Why it happens:** No todas las librerías respetan las variables de entorno de proxy. `asyncssh` tiene su propio mecanismo de conectividad. `librouteros` usa sockets TCP directos sin soporte de proxy.

**How to avoid:** Verificar explícitamente en Phase 2 que cada librería de colección de datos (librouteros, asyncssh, aiohttp) puede rutear tráfico a través de SOCKS5. Si alguna no puede, evaluar: (a) usar un wrapper que inyecte el proxy, o (b) mover worker a on-premises.

**Warning signs:** El worker puede hacer ping a hosts de Tailscale pero `librouteros.connect()` a IPs privadas del ISP falla con `connection refused` o `timeout`.

### Pitfall 6: DATABASE_URL format incorrecto para asyncpg

**What goes wrong:** Railway provee `DATABASE_URL` con formato `postgresql://user:pass@host:5432/db`. asyncpg y SQLAlchemy async requieren `postgresql+asyncpg://...`.

**How to avoid:** En `config.py`, reemplazar el prefix al construir el URL para el engine:
```python
# En core/config.py o database.py
async_db_url = settings.DATABASE_URL.replace(
    "postgresql://", "postgresql+asyncpg://"
)
```

---

## Runtime State Inventory

Esta es una fase de infraestructura nueva (greenfield) — no hay renombrados ni migraciones de datos existentes.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | Ninguno — base de datos nueva | Crear schema con Alembic 001_initial_schema |
| Live service config | Ninguno — Railway services no existen aún | Crear servicios en Railway dashboard |
| OS-registered state | Ninguno | N/A |
| Secrets/env vars | Ninguna — generar FERNET_KEY, SECRET_KEY, obtener TAILSCALE_AUTH_KEY | Generar y cargar en Railway antes del primer deploy |
| Build artifacts | Ninguno | N/A |

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.12+ | Backend runtime | ✓ | 3.14.3 (local) | Dockerfile especifica python:3.12-slim |
| pip | Package install | ✓ | disponible | — |
| Railway CLI | Deploy | No verificado | — | Railway dashboard web |
| PostgreSQL (Railway managed) | INFRA-02 | Requiere crear addon | — | No hay fallback (requerimiento locked) |
| Redis (Railway managed) | Celery broker | Requiere crear addon | — | No hay fallback (requerimiento locked) |
| Tailscale auth key | INFRA-01 | Requiere cuenta Tailscale | — | Worker on-premises en red ISP |
| RouterOS v7 Mikrotik con IP pública | INFRA-01 | [ASSUMED] disponible en BEEPYRED | — | Confirmar con técnico antes de comenzar |

**Missing dependencies con fallback:**
- Tailscale auth key: crear cuenta gratuita en tailscale.com, generar auth key efímera para el worker. Fallback si Tailscale no es viable: mover worker Celery a servidor en red ISP.

**Confirmación requerida antes de ejecutar Phase 1:**
- ¿El Mikrotik core tiene IP pública fija? (necesario para endpoint del servidor WireGuard / Tailscale subnet router)
- ¿Es aceptable usar Tailscale SaaS como coordinador VPN? (alternativa: Headscale self-hosted)

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest + pytest-asyncio |
| Config file | `backend/pytest.ini` — crear en Wave 0 |
| Quick run command | `cd backend && pytest tests/ -x -q --timeout=10` |
| Full suite command | `cd backend && pytest tests/ -v --timeout=30` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| INFRA-01 | VPN tunnel: worker puede alcanzar IP en red privada ISP | Smoke (manual) | `ping -c 3 <equipo_privado>` desde Railway worker | N/A — manual |
| INFRA-01 | Tailscale inicia correctamente (logs no muestran error) | Integration | `pytest tests/test_vpn_health.py -x` | ❌ Wave 0 |
| INFRA-02 | DB connection exitosa y schema correcto | Integration | `pytest tests/test_db.py::test_schema_exists -x` | ❌ Wave 0 |
| INFRA-02 | Alembic migrations corren sin error | Integration | `cd backend && alembic upgrade head` | ❌ Wave 0 |
| INFRA-02 | Todas las tablas existen con columnas esperadas | Integration | `pytest tests/test_db.py::test_all_tables -x` | ❌ Wave 0 |
| INFRA-03 | No hay strings de credenciales hardcodeadas en el código | Static analysis | `grep -r "password\|secret\|token\|key" backend/app/ --include="*.py" -l` | N/A — comando |
| DEPLOY-01 | web service responde GET /health con 200 | Smoke | `curl https://<railway-url>/health` | N/A — Railway |
| DEPLOY-01 | worker Celery arranca sin errores (check logs Railway) | Smoke (manual) | Revisar Railway logs | N/A — manual |
| DEPLOY-01 | beat Celery arranca sin errores | Smoke (manual) | Revisar Railway logs | N/A — manual |
| DEPLOY-03 | `encrypt_credential` + `decrypt_credential` roundtrip | Unit | `pytest tests/test_security.py::test_fernet_roundtrip -x` | ❌ Wave 0 |
| DEPLOY-03 | Datos en `device_credentials` no son texto plano en DB | Integration | `pytest tests/test_db.py::test_credentials_encrypted -x` | ❌ Wave 0 |

**Verificación de éxito por criterio (definición de done):**

1. **INFRA-01 (VPN):** Desde el Railway worker, `curl http://<IP_equipo_privado>` retorna respuesta (no timeout). Verificar con un equipo de la red interna del ISP.
2. **INFRA-02 (DB):** `SELECT table_name FROM information_schema.tables WHERE table_schema='public'` retorna exactamente: `devices`, `device_credentials`, `metrics`, `alerts`, `incidents`, `onus`, `alembic_version`.
3. **DEPLOY-01 (Railway):** Los tres servicios (web, worker, beat) aparecen en Railway dashboard con status "Deployed" y sin restarts en las últimas 24h.
4. **INFRA-03/DEPLOY-03 (Credenciales):** `grep -r "DATABASE_URL\|REDIS_URL\|FERNET_KEY\|TELEGRAM" backend/app/` retorna únicamente referencias a `settings.<variable>`, nunca valores literales.

### Wave 0 Gaps (tests que deben crearse antes de implementar)

- [ ] `backend/pytest.ini` — configuración de pytest con asyncio_mode = auto
- [ ] `backend/tests/__init__.py` — vacío
- [ ] `backend/tests/conftest.py` — fixtures: async db session, Fernet instance con key de test
- [ ] `backend/tests/test_db.py` — test_schema_exists, test_all_tables, test_credentials_encrypted
- [ ] `backend/tests/test_security.py` — test_fernet_roundtrip, test_fernet_invalid_key_raises
- [ ] `backend/tests/test_vpn_health.py` — test_tailscale_running (verifica proceso, no conectividad real)
- [ ] Framework install: `pip install pytest pytest-asyncio pytest-cov`

---

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | Parcial en Phase 1 | Solo `SECRET_KEY` para JWT futuro — Phase 2 implementa auth |
| V3 Session Management | No — Phase 2 | N/A |
| V4 Access Control | No — Phase 2 | N/A |
| V5 Input Validation | Sí | Pydantic v2 valida todos los Settings y modelos |
| V6 Cryptography | Sí — CRÍTICO | `cryptography.fernet.Fernet` para credenciales de equipos — nunca implementación propia |
| V7 Error Handling | Sí | No exponer stack traces ni credenciales en logs |

### Known Threat Patterns for This Stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Credenciales en código fuente | Information Disclosure | pydantic-settings desde env vars; .gitignore para .env; grep en CI |
| Fernet key en logs | Information Disclosure | No loggear `settings.FERNET_KEY`; usar `SecretStr` en pydantic |
| DB credentials en URL plano | Information Disclosure | Railway injected env vars; nunca hardcodear en Dockerfile |
| Conexión DB sin SSL | Tampering / Interception | Railway PostgreSQL usa SSL por defecto; verificar `sslmode=require` |
| SQL injection vía ORM bypass | Tampering | Usar SQLAlchemy ORM/Core — nunca f-string SQL; solo text() con bindparams |
| WireGuard private key expuesta | Elevation of Privilege | Almacenar como Railway env var; nunca en archivos de config en git |

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Alembic síncrono con psycopg2 | Alembic async con asyncpg + `async_engine_from_config` | Alembic 1.11+ (2022) | env.py debe ser async para no bloquear el event loop |
| WireGuard en Docker con NET_ADMIN | Tailscale userspace o agente on-premises | 2023-2024 (Railway restricción) | Arquitectura de VPN debe adaptarse a Railway sin privilegios |
| `celery worker -B` en producción | Beat como servicio separado | Siempre fue recomendación; más crítico con multi-instance | Evita duplicación de tareas periódicas |
| Celery 4.x con kombu | Celery 5.6+ con redis nativo | 2021-2022 | API más limpia, mejor soporte de asyncio en tasks |
| pydantic v1 `BaseSettings` | pydantic-settings separado (v2) | pydantic 2.0 (2023) | `BaseSettings` ya no está en pydantic core — instalar `pydantic-settings` por separado |
| `Fernet` de `cryptography < 3.x` | `cryptography 47.x` | 2024-2025 | API idéntica, mejoras de rendimiento y seguridad |

**Deprecated/outdated:**
- `python-jose`: tiene vulnerabilidades conocidas (CVE-2024-33664). Para Phase 1 no se usa JWT, pero cuando llegue Phase 2 auth, considerar `python-jwt` o `joserfc` como alternativa. [ASSUMED - verificar CVEs actuales]
- `passlib`: sin actualizaciones recientes. Para Phase 2, considerar `argon2-cffi` para hashing de passwords.

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `librouteros` no tiene soporte nativo de SOCKS5 proxy | Architecture Patterns (Tailscale) | Si tiene soporte, Tailscale userspace funcionaría para Phase 3. Sin soporte, worker debe ir on-premises |
| A2 | `asyncssh` tiene soporte limitado de SOCKS5 proxy | Architecture Patterns (Tailscale) | Igual que A1 — impacta viabilidad de Tailscale userspace para VSOL SSH |
| A3 | `aiohttp` + `aiohttp-socks` soportan SOCKS5 | Architecture Patterns | Si no funciona, Ubiquiti REST API (Phase 5) no puede ir por Tailscale |
| A4 | El Mikrotik de BEEPYRED tiene IP pública fija | Environment Availability | Sin IP pública, WireGuard server no es accesible — requiere rediseño |
| A5 | Tailscale free tier es aceptable para el proyecto | Architecture Patterns | Si no, evaluar Headscale self-hosted en un VPS barato |
| A6 | `python-jose` tiene CVEs activos en 2026 | Security Domain | Si fue parchado, puede seguir usándose para Phase 2 JWT |
| A7 | TimescaleDB Railway managed addon está disponible en el tier de Railway del proyecto | Standard Stack | Si no, las métricas van a PostgreSQL vanilla con particionamiento manual o tabla simple |
| A8 | El schema de tablas definido cubre todos los campos de Phase 3-5 | Architecture Patterns (schema) | Si faltan campos críticos, requerirá migraciones adicionales en fases posteriores |

---

## Open Questions (RESOLVED)

1. **¿Librouteros, asyncssh, y aiohttp soportan SOCKS5 proxy?**
   - **Deferred to Phase 2** — test de conectividad SOCKS5 incluido en plan de Phase 2 antes de asumir compatibilidad completa.

2. **¿El Mikrotik de BEEPYRED tiene IP pública fija disponible?**
   - **RESOLVED** — El técnico confirmó que hay un Mikrotik con IP pública fija. Actúa como Tailscale subnet router.

3. **¿Usar Tailscale SaaS o Headscale self-hosted como coordinador VPN?**
   - **RESOLVED** — Tailscale SaaS confirmado por el técnico (CONTEXT.md 2026-04-25). No se usa Headscale.

4. **¿TimescaleDB disponible en el addon PostgreSQL de Railway?**
   - **RESOLVED** — No se usa TimescaleDB. PostgreSQL puro con BRIN index en `recorded_at` confirmado por el técnico (CONTEXT.md 2026-04-25).

5. **¿Correr Alembic migrations en startup del contenedor o como paso separado?**
   - **RESOLVED** — Alembic migrations se ejecutan como Railway pre-deploy command (no en startup del contenedor). Documentado en railway.toml como instrucción de operador.

---

## Sources

### Primary (HIGH confidence)
- PyPI registry via `pip index versions` — versiones verificadas de todos los paquetes Python el 2026-04-25
- MikroTik official docs [help.mikrotik.com/docs/spaces/ROS/pages/69664792/WireGuard] — RouterOS v7 WireGuard CLI commands
- Tailscale userspace networking docs [tailscale.com/docs/concepts/userspace-networking] — TS_USERSPACE=1 requirements y limitaciones
- Celery official docs [docs.celeryq.dev/en/stable/userguide/periodic-tasks.html] — beat service separation recommendation
- Railway Help Station [station.railway.com/feedback/allow-services-to-be-run-in-privileged-m-8c66b22b] — NET_ADMIN / privileged mode not supported
- cryptography.io Fernet docs [cryptography.io/en/latest/fernet/] — versión 47.0.0 confirmada en PyPI

### Secondary (MEDIUM confidence)
- berkkaraal.com/blog (2024) — Alembic async env.py configuration pattern, verified against Alembic official cookbook
- Railway config-as-code docs [docs.railway.com/config-as-code/reference] — railway.toml `startCommand` format
- Railway monorepo docs [docs.railway.com/guides/monorepo] — multi-service desde monorepo
- railway.com/deploy/fastapi-celery-beat-worker-flower — Railway official template confirming beat as separate service

### Tertiary (LOW confidence)
- WebSearch: "librouteros SOCKS5 proxy support" — no encontrado; asumido como no soportado
- WebSearch: "asyncssh SOCKS5 proxy Docker" — limitado; clasificado como ASSUMED

---

## Metadata

**Confidence breakdown:**
- Standard stack (versiones): HIGH — verificadas contra PyPI registry en vivo
- WireGuard en Railway: HIGH (no es posible) — verificado contra Railway Help Station oficial
- Tailscale userspace: MEDIUM — documentación oficial confirma funcionalidad, pero compatibilidad con librerías específicas (librouteros, asyncssh) no verificada
- RouterOS v7 WireGuard config: HIGH — documentación oficial MikroTik
- PostgreSQL schema: MEDIUM — diseño propio basado en requirements, no validado contra equipo real
- Alembic async config: HIGH — patrón documentado en Alembic cookbook oficial
- Fernet encryption: HIGH — librería estándar, bien documentada, versión verificada en PyPI
- Celery beat separado: HIGH — recomendación explícita de docs oficiales de Celery

**Research date:** 2026-04-25
**Valid until:** 2026-05-25 (30 días — stack estable, pero Railway policies pueden cambiar)
