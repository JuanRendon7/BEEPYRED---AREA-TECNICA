<!-- GSD:project-start source:PROJECT.md -->
## Project

**BEEPYRED NOC — Network Operations Center**

Plataforma web de monitoreo de red en tiempo real para BEEPYRED ISP GROUP SAS, proveedor de internet en San Luis, Antioquia. Consolida en un solo dashboard el estado de todos los equipos de la red: Mikrotik, OLTs VSOL, ONUs GPON, radioenlaces Ubiquiti y Mimosa. Diseñada para uso del técnico de red con alertas inmediatas vía Telegram e historial de incidentes.

**Core Value:** El técnico debe poder ver en un solo vistazo qué equipo está caído o degradado, sin tener que entrar a cada equipo individualmente.

### Constraints

- **Conectividad:** Los equipos están en red privada — el servidor NOC debe poder alcanzarlos (VPN o IP pública en equipos core)
- **Protocolo principal:** Mikrotik API + SSH/Telnet para VSOL; evitar SNMP donde haya mejor alternativa nativa
- **Deploy:** Railway (Node.js/Python compatible) con dominio personalizado
- **Usuario único v1:** Un solo técnico; sin necesidad de roles complejos en v1
- **Tiempo real:** Polling cada 30-60 segundos es suficiente; no se requiere streaming sub-segundo
<!-- GSD:project-end -->

<!-- GSD:stack-start source:research/STACK.md -->
## Technology Stack

## Recommended Stack
### Decision Summary (TL;DR)
### Core Framework: Backend
| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| Python | 3.12 | Runtime | Native async/await, rich networking libs (paramiko, asyncssh, librouteros), largest ISP tooling ecosystem. Node.js alternative exists but Python dominates network automation. |
| FastAPI | 0.111+ | REST API + WebSocket server | Async-first, auto OpenAPI docs, native WebSocket support for real-time dashboard push, excellent type safety with Pydantic v2. Outperforms Flask/Django for this workload. |
| Uvicorn | 0.29+ | ASGI server | Production-grade, works with Gunicorn workers for Railway deployment, required by FastAPI. |
| Pydantic v2 | 2.7+ | Data validation & serialization | 5-17x faster than v1 (Rust core), validates all device API responses before storing, ensures data consistency across vendors. |
- `librouteros` (Mikrotik RouterOS API) is Python-native; Node.js has no equivalent maintained library
- `asyncssh` and `paramiko` for SSH to VSOL OLTs are Python-only, mature, battle-tested
- Network automation tooling (Netmiko, Napalm) is 95% Python; reusing community patterns is valuable
- asyncio handles 500+ concurrent connections with connection pooling without threads
- Node.js would require re-implementing SSH parsers for OLT command output — significant custom work
### Concurrent Polling Architecture
| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| asyncio | stdlib (Python 3.12) | Concurrent I/O scheduling | Polling 500 devices is I/O-bound, not CPU-bound. asyncio handles thousands of concurrent connections with a single thread using cooperative multitasking. No threads needed. |
| asyncssh | 2.14+ | Async SSH client | Zero-thread SSH to VSOL OLTs and Ubiquiti devices. Supports connection pooling, host key management, command streaming. |
| librouteros | 3.2+ | Mikrotik RouterOS API client | Official protocol implementation (port 8728/8729), async-compatible, structured data return (no SSH parsing needed). |
| aiohttp | 3.9+ | Async HTTP client | For Ubiquiti UISP REST API and Mimosa REST API calls. Built-in connection pooling, timeout control, session reuse. |
| APScheduler | 3.10+ | Polling scheduler | Schedules polling jobs per device with configurable intervals (30-60s). Integrates with asyncio event loop. Handles missed jobs gracefully. |
# Pattern: asyncio.gather with semaphore to limit concurrency
- 500 devices / 50 concurrent = 10 batches, each completing in ~2-5s
- Total poll cycle: 20-50 seconds — fits within 60s interval
- Semaphore prevents overwhelming devices or Railway's egress
### Database
| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| PostgreSQL | 16 | Primary database | Device inventory, incident history, alert config, user auth. Relational model fits structured network data. Railway has native PostgreSQL addon. |
| TimescaleDB | 2.14+ | Time-series metrics extension | Extends PostgreSQL for high-frequency metric storage (CPU, RAM, latency, optical signal). Automatic data compression and time-based partitioning. Alternative: InfluxDB, but TimescaleDB keeps a single DB to manage. |
| Redis | 7.2 | Cache + pub/sub + job queue | Three roles: (1) Cache last-known device state for instant dashboard loads, (2) Pub/sub channel for WebSocket fan-out to connected browsers, (3) Celery broker for background jobs. Railway has Redis addon. |
| SQLAlchemy | 2.0+ | ORM (async mode) | Async ORM with `asyncpg` driver. SQLAlchemy 2.0 has first-class async support. Use for inventory/incidents/config, not for metrics (raw SQL for TimescaleDB queries). |
| asyncpg | 0.29+ | PostgreSQL async driver | Fastest Python PostgreSQL driver, required for SQLAlchemy async mode. 3x faster than psycopg2 for bulk writes. |
| Alembic | 1.13+ | Database migrations | Standard SQLAlchemy migration tool. Generates versioned migration files, safe for Railway deployments. |
- Adding InfluxDB means a third database to manage (Postgres + Redis + InfluxDB)
- TimescaleDB is a PostgreSQL extension — same connection, same backup, same Railway service
- Prometheus is pull-based and designed for server metrics, not device API data; adapting it adds complexity
- For 500 devices at 60s intervals = ~8 metrics/device = 4,000 rows/minute — well within TimescaleDB's range
### Background Jobs
| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| Celery | 5.3+ | Task queue for polling workers | Distributes device polling across worker processes. Each Celery worker runs its own asyncio event loop. Allows scaling horizontally by adding Railway worker services. |
| celery-beat | (included) | Periodic task scheduler | Replaces APScheduler for production. Stores schedule in Redis, survives restarts, supports per-device polling intervals. |
### Device Integration Libraries
| Library | Version | Device Type | Notes |
|---------|---------|-------------|-------|
| librouteros | 3.2+ | Mikrotik RouterOS | Pure Python, async-compatible, implements RouterOS API protocol (port 8728 plain, 8729 SSL). Returns structured Python dicts. Use for: interface stats, system resources, DHCP leases. |
| asyncssh | 2.14+ | VSOL OLT, Ubiquiti AirOS | Async SSH with connection pooling. For VSOL: send CLI commands, parse text output. For Ubiquiti SSH fallback: same approach. |
| aiohttp | 3.9+ | Ubiquiti UISP, Mimosa REST | HTTP client for REST APIs. UISP API uses Bearer token auth. Mimosa uses Basic/Token auth over HTTPS. |
| python-telegram-bot | 21.x | Telegram alerts | Official Telegram Bot API wrapper. Use `send_message` with Markdown formatting for alerts. Async-native in v21+. |
### Core Framework: Frontend
| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| React | 18.3+ | UI framework | Component model fits dashboard panels. Large ecosystem for charts, tables, maps. Concurrent mode for non-blocking UI updates. |
| Vite | 5.x | Build tool | 10-100x faster than CRA/Webpack. Native ESM, HMR in <100ms. Railway builds from Dockerfile — fast Vite builds matter. |
| TypeScript | 5.4+ | Type safety | Prevents runtime errors in dashboard state management. Essential when handling heterogeneous device data (Mikrotik, VSOL, Ubiquiti, Mimosa all return different shapes). |
| shadcn/ui | latest | UI component library | Not a dependency — copies components into your codebase. Uses Radix UI primitives + Tailwind. No version lock-in. Excellent for data tables, badges, status indicators. |
| Tailwind CSS | 3.4+ | Utility CSS | Pairs with shadcn/ui. Rapid styling of status indicators (red/yellow/green device cards). |
| Recharts | 2.12+ | Charts | React-native charting library. Line charts for latency/traffic history, bar charts for ONU signal distribution. Lighter than Chart.js, easier than D3 for this use case. |
| TanStack Query | 5.x | Server state management | Handles polling intervals for REST endpoints, stale-while-revalidate caching, background refetch. Replaces Redux for server state. |
| React Router | 6.x | Client-side routing | Dashboard view, device detail, incidents log, inventory — multi-page SPA. |
- Server-side rendering adds complexity without benefit for an internal tool used by one technician
- NOC dashboard is a SPA — all data is real-time, SSR provides no SEO or performance value
- Railway deploys a static Vite build served by Nginx or a FastAPI static file handler — simpler than Next.js runtime
- React has the largest ecosystem for monitoring/dashboard components
- The team is building for a single operator; framework preference matters less than library availability
- Recharts, TanStack Query, and shadcn/ui are React-specific
### Real-Time Communication
| Technology | Purpose | Why |
|------------|---------|-----|
| WebSocket (FastAPI native) | Push device status updates to browser | FastAPI has built-in WebSocket support. No additional library needed. When Celery worker polls a device, result goes to Redis pub/sub, FastAPI WebSocket handler reads Redis and pushes to all connected browsers. |
| Redis pub/sub | Worker-to-API message bus | Decouples polling workers from WebSocket server. Workers don't need to know about connected clients. |
# FastAPI endpoint
### Authentication
| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| python-jose | 3.3+ | JWT token generation/validation | Stateless auth tokens. Single user in v1, but JWT allows easy expansion to multiple users later. |
| passlib | 1.7+ | Password hashing | bcrypt hashing. Standard for FastAPI auth. |
| FastAPI security | (built-in) | OAuth2 password flow | FastAPI's built-in `OAuth2PasswordBearer` handles token extraction from headers. No external auth service needed for v1 single-user scenario. |
### Infrastructure & Deployment
| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| Docker | latest | Container runtime | Railway deploys from Dockerfile. Containerization ensures parity between dev and production. Multi-stage build keeps image lean. |
| Railway | current | PaaS host | Supports Dockerfile deployments, managed PostgreSQL, managed Redis, custom domains, environment variables per service, automatic HTTPS. |
| Nginx | 1.25+ | Static file server | Serves the compiled React/Vite frontend. Can be a separate Railway service or bundled with FastAPI using `StaticFiles`. For v1, bundle with FastAPI to minimize Railway service count (affects billing). |
| Gunicorn + Uvicorn workers | latest | Production ASGI server | Gunicorn manages multiple Uvicorn worker processes for Railway's single-container deployment. Formula: `workers = 2 * CPU cores + 1`. |
- 3 services from 1 Docker image (different start commands) = minimal maintenance
- Railway's free tier may not cover 3 services; Hobby plan ($5/month) covers unlimited services
- Worker service needs network access to device IPs — verify Railway egress IPs are reachable from the ISP network or configure VPN
# Stage 1: Build React frontend
# Stage 2: Python backend
### Telegram Alerts
| Technology | Version | Purpose | Notes |
|------------|---------|---------|-------|
| python-telegram-bot | 21.3+ | Send alert messages | Async-native. Use `bot.send_message(chat_id=CHAT_ID, text=message, parse_mode="Markdown")`. No webhook needed — just outbound calls from Celery worker when threshold crossed. |
## Alternatives Considered
| Category | Recommended | Alternative | Why Not |
|----------|-------------|-------------|---------|
| Backend language | Python 3.12 | Node.js (Express/Fastify) | No maintained Mikrotik RouterOS API library for Node; SSH parsing libraries less mature |
| Backend framework | FastAPI | Django + DRF | Django is synchronous-first; async support is bolted on; heavier ORM overhead; no built-in WebSocket |
| Backend framework | FastAPI | Flask | No native async, no WebSocket, no auto-validation |
| Task queue | Celery | RQ (Redis Queue) | RQ lacks Celery-beat equivalent for complex schedules; smaller ecosystem |
| Task queue | Celery | asyncio only (no Celery) | No persistence if web process crashes; can't scale workers independently |
| Metrics DB | TimescaleDB | InfluxDB | Third database to manage; separate query language; extra Railway service |
| Metrics DB | TimescaleDB | Prometheus | Pull-based model doesn't fit SSH/API polling architecture; designed for server metrics not device APIs |
| Frontend | React + Vite | Next.js | SSR overhead for internal SPA with no SEO need; more Railway config required |
| Frontend | React + Vite | Vue 3 | Fewer dashboard component libraries; shadcn/ui is React-specific |
| Charts | Recharts | Chart.js | Chart.js is canvas-based, harder to integrate with React state; Recharts is declarative/reactive |
| Charts | Recharts | D3.js | D3 requires manual DOM manipulation; overkill for standard line/bar charts |
| Auth | JWT + python-jose | Auth0 / Supabase Auth | External auth service adds cost and complexity for a single-user v1 internal tool |
| Deployment | Railway | Render | Railway has better multi-service coordination; both are valid; Railway mentioned in project requirements |
| Deployment | Railway | VPS (DigitalOcean) | VPS requires server management; Railway is PaaS — simpler for this team |
## What NOT to Use
| Technology | Why Avoid |
|------------|-----------|
| SNMP (as primary) | PROJECT.md explicitly states "evitar SNMP donde haya mejor alternativa nativa". RouterOS API and SSH give richer, structured data. |
| Django | Synchronous-first framework — polling 500 devices concurrently requires async throughout; Django's ORM blocks the event loop |
| threading.Thread | Use asyncio instead. Threads have GIL contention, memory overhead, and race conditions. asyncio handles 500 I/O-bound connections with a single thread. |
| Socket.io | WebSocket protocol overhead. FastAPI's native WebSocket is sufficient and lighter. |
| GraphQL | No client-driven query optimization need for 1 user internal tool. REST is simpler to implement and debug. |
| MongoDB | Unstructured device data benefits from schema enforcement (Pydantic + SQLAlchemy). TimescaleDB handles the time-series part that MongoDB's performance suffers at scale. |
| React Native | PROJECT.md: "App móvil nativa — out of scope v1". Responsive web is sufficient. |
| Kubernetes | Overkill for 1 ISP NOC on Railway. Railway handles orchestration. |
## Installation
### Backend dependencies (requirements.txt)
### Frontend dependencies (package.json)
## Railway Environment Variables
# Database
# Security
# Telegram
# Polling
# Railway auto-sets PORT — bind to 0.0.0.0:$PORT
## Network Connectivity Note
## Confidence Assessment
| Area | Confidence | Notes |
|------|------------|-------|
| Python + FastAPI for backend | HIGH | Well-established; training data consistent with official docs through Aug 2025 |
| asyncio + asyncssh for concurrent polling | HIGH | Standard pattern; confirmed capability |
| librouteros for Mikrotik | HIGH | Active maintained library, RouterOS API is stable |
| TimescaleDB for metrics | HIGH | Mature extension, widely used for ISP monitoring |
| Celery + Redis for workers | HIGH | Standard Python task queue stack |
| React + Vite + shadcn/ui for frontend | HIGH | Dominant pattern in 2024-2025 internal tooling |
| FastAPI WebSocket + Redis pub/sub | HIGH | Documented FastAPI pattern |
| VSOL OLT SSH CLI parsing | MEDIUM | VSOL CLI behavior known but specific model command syntax needs hands-on validation |
| Mimosa REST API endpoints | MEDIUM | API exists but endpoint compatibility with specific firmware versions needs validation |
| Railway multi-service deployment | HIGH | Railway docs support this pattern; pricing depends on current Railway plans |
| Network reachability from Railway | LOW | Completely depends on ISP network topology — must be validated before dev starts |
## Sources
- FastAPI official: https://fastapi.tiangolo.com
- librouteros PyPI: https://pypi.org/project/librouteros/
- asyncssh docs: https://asyncssh.readthedocs.io
- TimescaleDB docs: https://docs.timescale.com
- Celery docs: https://docs.celeryq.dev
- python-telegram-bot docs: https://python-telegram-bot.readthedocs.io
- Railway docs: https://docs.railway.com
- shadcn/ui: https://ui.shadcn.com
- TanStack Query: https://tanstack.com/query/latest
<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->
## Conventions

Conventions not yet established. Will populate as patterns emerge during development.
<!-- GSD:conventions-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->
## Architecture

Architecture not yet mapped. Follow existing patterns found in the codebase.
<!-- GSD:architecture-end -->

<!-- GSD:skills-start source:skills/ -->
## Project Skills

No project skills found. Add skills to any of: `.claude/skills/`, `.agents/skills/`, `.cursor/skills/`, or `.github/skills/` with a `SKILL.md` index file.
<!-- GSD:skills-end -->

<!-- GSD:workflow-start source:GSD defaults -->
## GSD Workflow Enforcement

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

Use these entry points:
- `/gsd-quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd-debug` for investigation and bug fixing
- `/gsd-execute-phase` for planned phase work

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.
<!-- GSD:workflow-end -->



<!-- GSD:profile-start -->
## Developer Profile

> Profile not yet configured. Run `/gsd-profile-user` to generate your developer profile.
> This section is managed by `generate-claude-profile` -- do not edit manually.
<!-- GSD:profile-end -->
