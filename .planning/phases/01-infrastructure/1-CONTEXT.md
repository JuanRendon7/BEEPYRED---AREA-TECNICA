# Phase 1: Infrastructure — Context

**Phase goal:** El entorno de ejecución del NOC está listo: Railway conecta a la red privada del ISP, PostgreSQL persiste todos los datos, y ninguna credencial existe en el código.

**Requirements:** INFRA-01, INFRA-02, INFRA-03, DEPLOY-01, DEPLOY-03

---

## Decisions

### VPN / Conectividad Railway → Red ISP

**Decision (REVISED 2026-04-25):** Tailscale userspace — Railway no permite NET_ADMIN por lo que WireGuard (kernel y userspace boringtun/wireguard-go) es imposible. Confirmado por el técnico.

- Railway corre Tailscale en modo userspace (`--tun=userspace-networking`) — no requiere NET_ADMIN
- Tailscale expone un proxy SOCKS5 en `localhost:1055` que los collectors (librouteros, asyncssh, aiohttp) deben usar vía `ALL_PROXY`
- El Mikrotik con IP pública actúa como **Tailscale subnet router** (anuncia las rutas de la red ISP privada a la red Tailscale)
- Tailscale SaaS (no Headscale self-hosted) — gratis hasta 100 nodos

**Implementation notes for planner:**
- Variable de entorno: `TAILSCALE_AUTH_KEY` (ephemeral key generada en el panel Tailscale)
- El worker Dockerfile instala `tailscale` en modo userspace en el stage worker
- Script `start-worker.sh`: arranca tailscaled → autentica → verifica conectividad → lanza Celery worker
- El Mikrotik debe tener Tailscale instalado y configurado como subnet router antes del deploy
- `ALL_PROXY=socks5://localhost:1055` debe estar seteado para que los collectors usen el tunnel
- **Punto de validación manual:** confirmar que `librouteros`, `asyncssh` y `aiohttp` respetan `ALL_PROXY` en Phase 2

### RouterOS Version

**Decision:** RouterOS v7 es la versión principal.

- La librería Python `librouteros` soporta v6 y v7
- La API binaria de RouterOS es compatible entre versiones para los endpoints usados (system/resource, interface, ip/address)
- Si hay equipos v6 en la red, el mismo collector funciona — no se necesita adaptador por versión para los endpoints de Phase 3

### Estructura del Repositorio

**Decision:** Monorepo único con /backend y /frontend.

```
beepyred-noc/
├── backend/           # FastAPI + Celery (Python)
│   ├── app/
│   │   ├── api/       # FastAPI routers
│   │   ├── collectors/ # Protocol adapters (Mikrotik, VSOL, Ubiquiti, Mimosa)
│   │   ├── models/    # SQLAlchemy models
│   │   ├── tasks/     # Celery tasks
│   │   └── core/      # Config, security, deps
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/          # React + Vite (Phase 2+)
│   └── ...
├── docker-compose.yml # Solo referencia local, no es el deploy target
├── railway.toml       # Configuración de Railway
└── .planning/
```

### Estrategia de Deploy

**Decision:** Railway directamente desde el inicio — sin entorno Docker Compose local.

- El desarrollo se hace en local (Python standard, sin Docker)
- Los cambios se pushean al repo Git; Railway hace el deploy automáticamente
- Para pruebas de conectividad VPN se usa Railway directamente (no hay forma de simularla localmente)
- **Railway services a crear:**
  - `web` — FastAPI (uvicorn)
  - `worker` — Celery worker
  - `beat` — Celery beat (scheduler)
  - `db` — PostgreSQL (Railway managed)
  - `redis` — Redis (Railway managed)

### Base de Datos

**Decision:** PostgreSQL Railway managed — sin TimescaleDB. Confirmado por el técnico.

- Sin almacenamiento local efímero (sin SQLite, sin archivos)
- Schema inicial en Phase 1 cubre: `devices`, `device_credentials`, `metrics`, `alerts`, `incidents`, `onus`
- Migraciones con Alembic async desde el día 1 (`alembic init -t async alembic`)
- Métricas: tabla `metrics` con particionamiento por mes y BRIN index en `recorded_at` — sin TimescaleDB
- Retención: las métricas y incidentes más viejos de 30 días se limpian automáticamente (Celery beat task)
- Alembic migrations se ejecutan como pre-deploy command en Railway (no en startup del contenedor web)

### Gestión de Credenciales

**Decision:** Dos capas de protección:

1. **Credenciales de infraestructura** (DB URL, Redis URL, Telegram token, WireGuard keys) → Variables de entorno Railway. Nunca en el código.
2. **Credenciales de equipos de red** (usuario/contraseña SSH, API keys Mikrotik, UISP API key, Mimosa passwords) → Almacenadas en PostgreSQL encriptadas con Fernet (clave de encriptación = variable de entorno `FERNET_KEY`).

---

## Out of Scope for Phase 1

- Frontend (Phase 2)
- Lógica de polling (Phase 2)
- Collectors de equipos (Phase 3+)
- Alertas Telegram (Phase 3)

---

## Open Questions for Research

- ¿Railway permite `NET_ADMIN` capability para WireGuard kernel module? Si no, investigar `boringtun` (WireGuard userspace en Rust) o `wireguard-go`
- ¿Cuál es el tier mínimo de Railway PostgreSQL que soporta las extensiones necesarias?
- ¿Cómo configurar múltiples servicios (web, worker, beat) desde un mismo repo en Railway usando `railway.toml`?

---

## Claude's Discretion

- Schema exacto de las tablas (columnas, tipos, índices) — el planner decide basado en los requisitos
- Nombre de las tablas y convenciones de nomenclatura — seguir snake_case Python estándar
- Versión exacta de librerías Python — el planner elige las más recientes estables
- Estructura interna de carpetas dentro de `/backend/app/` — el planner puede ajustar

---
*Created: 2026-04-25 | Phase: 1 — Infrastructure*
