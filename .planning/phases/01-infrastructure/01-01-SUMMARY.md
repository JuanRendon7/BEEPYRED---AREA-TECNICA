---
phase: 01-infrastructure
plan: "01"
subsystem: backend-scaffold
tags: [infrastructure, docker, tailscale, pydantic-settings, celery, railway]
dependency_graph:
  requires: []
  provides:
    - backend-monorepo-structure
    - dockerfile-multi-stage
    - pydantic-settings-config
    - railway-web-service-config
    - env-template
    - test-stubs-infra01-infra03
  affects:
    - all-subsequent-backend-plans
tech_stack:
  added:
    - fastapi==0.136.1
    - uvicorn[standard]==0.46.0
    - gunicorn==22.0.0
    - pydantic==2.13.3
    - pydantic-settings==2.10.1
    - sqlalchemy[asyncio]==2.0.49
    - asyncpg==0.31.0
    - alembic==1.18.4
    - celery[redis]==5.6.3
    - redis==7.4.0
    - cryptography==47.0.0
    - python-dotenv==1.2.2
    - httpx==0.28.1
    - pytest==8.3.5
    - pytest-asyncio==0.25.3
    - pytest-cov==6.1.0
  patterns:
    - pydantic-settings BaseSettings for all env var management
    - Docker multi-stage build (base/web/worker/beat)
    - Tailscale userspace networking via SOCKS5 proxy
    - Celery with Redis broker/backend
key_files:
  created:
    - backend/Dockerfile
    - backend/requirements.txt
    - backend/app/__init__.py
    - backend/app/main.py
    - backend/app/celery_app.py
    - backend/app/api/__init__.py
    - backend/app/collectors/__init__.py
    - backend/app/core/__init__.py
    - backend/app/core/config.py
    - backend/app/models/__init__.py
    - backend/app/tasks/__init__.py
    - backend/scripts/start-worker.sh
    - backend/.dockerignore
    - backend/tests/__init__.py
    - backend/tests/unit/__init__.py
    - backend/tests/unit/test_no_secrets.py
    - backend/tests/unit/test_vpn_health.py
    - backend/railway.toml
    - .env.example
    - .gitignore
  modified: []
decisions:
  - "Tailscale SaaS userspace (--tun=userspace-networking) confirmed as VPN mechanism — Railway blocks NET_ADMIN making kernel-mode WireGuard and boringtun impossible"
  - "FERNET_KEY and SECRET_KEY typed as SecretStr to prevent accidental logging"
  - "railway.toml configures web service only; worker and beat use same Dockerfile with different startCommand in Railway dashboard"
  - "alembic upgrade head documented as Railway pre-deploy command (not web startup)"
  - "CUSTOM_DOMAIN included in Settings now for Phase 6 DNS config (DEPLOY-02 prep)"
metrics:
  duration: "~25 minutes"
  completed_date: "2026-04-26"
  tasks_completed: 2
  tasks_total: 2
  files_created: 20
  files_modified: 0
---

# Phase 01 Plan 01: Scaffold and Config Summary

**One-liner:** FastAPI/Celery monorepo scaffold with Tailscale userspace VPN worker stage, pydantic-settings config, and Railway web service configuration.

## What Was Built

### Task 1: Monorepo Scaffold and Multi-Stage Dockerfile

Created the complete backend directory structure under `backend/` with all required Python packages (8 `__init__.py` files), a multi-stage Dockerfile with 4 stages, and unit test stubs for security and VPN verification.

**Dockerfile stages:**
- `base` — Python 3.12-slim with curl/ping and all Python deps installed
- `web` — inherits base, exposes 8000, launches Gunicorn with UvicornWorker
- `worker` — inherits base, installs Tailscale, copies and runs `start-worker.sh`
- `beat` — inherits base, launches `celery beat` with PersistentScheduler

**start-worker.sh flow:**
1. Starts `tailscaled --tun=userspace-networking --socks5-server=localhost:1055`
2. Waits 3 seconds for daemon to be ready
3. Authenticates with `tailscale up --authkey="${TAILSCALE_AUTH_KEY}"` accepting ISP subnet routes
4. Exports `ALL_PROXY=socks5://localhost:1055` (and HTTP/HTTPS variants) for collectors
5. Launches Celery worker with `exec` (replaces shell process)

**Test stubs created:**
- `test_no_secrets.py` (INFRA-03): scans all Python files for Tailscale auth keys (`tskey-auth-`), Fernet tokens (`gAAAAA`), and OpenAI keys; verifies `.env.example` uses CHANGE_ME placeholders
- `test_vpn_health.py` (INFRA-01): verifies `start-worker.sh` contains `--tun=userspace-networking`, `${TAILSCALE_AUTH_KEY}`, `ALL_PROXY=socks5://localhost:1055`, Celery launch; verifies Dockerfile has `AS worker` stage with tailscale

### Task 2: pydantic-settings Config, railway.toml, and .env.example

**`backend/app/core/config.py`** uses `pydantic-settings` v2 `BaseSettings` with:
- `DATABASE_URL`, `REDIS_URL` — provided automatically by Railway addons
- `SECRET_KEY: SecretStr`, `FERNET_KEY: SecretStr` — never appear in logs/repr
- `TAILSCALE_AUTH_KEY: str = ""` — only worker service sets this in Railway
- Telegram, polling intervals, alert thresholds, PORT, CUSTOM_DOMAIN all typed and defaulted

**`backend/railway.toml`** configures the web service:
- `buildTarget = "web"` — uses the web stage of the multi-stage Dockerfile
- `healthcheckPath = "/health"` — Railway monitors the FastAPI /health endpoint
- Documents `alembic upgrade head` as pre-deploy command (not in web startup)
- Documents startCommands for worker and beat (configured in Railway dashboard)

**`.env.example`** provides:
- All variables with CHANGE_ME placeholders (3 occurrences)
- Generation instructions for SECRET_KEY and FERNET_KEY
- Technical explanation of Tailscale decision (NET_ADMIN blocked, WireGuard impossible)
- `TAILSCALE_AUTH_KEY=tskey-auth-CHANGE_ME` placeholder

## Key Decision: Tailscale SaaS Userspace VPN

**Locked decision confirmed by the BEEPYRED technician:**

Railway containers do not have `NET_ADMIN` capability. This makes kernel-mode WireGuard, boringtun, and wireguard-go all impossible. Tailscale userspace mode (`--tun=userspace-networking`) works without `NET_ADMIN` and exposes a SOCKS5 proxy at `localhost:1055`.

The Mikrotik router with a fixed public IP acts as a Tailscale subnet router, announcing the ISP's private network routes into the Tailscale mesh. The Celery worker connects through this tunnel using `ALL_PROXY=socks5://localhost:1055`.

**Validation required in Phase 2:** confirm that `librouteros`, `asyncssh`, and `aiohttp` respect `ALL_PROXY` when connecting to ISP devices.

## Variables de Entorno Requeridas

| Variable | Required By | How to Generate |
|----------|-------------|-----------------|
| `DATABASE_URL` | web, worker, beat | Railway auto-provides with PostgreSQL addon |
| `REDIS_URL` | web, worker, beat | Railway auto-provides with Redis addon |
| `SECRET_KEY` | web (Phase 2 JWT) | `python -c "import secrets; print(secrets.token_hex(32))"` |
| `FERNET_KEY` | worker (device creds) | `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` |
| `TAILSCALE_AUTH_KEY` | worker only | Tailscale admin panel — ephemeral key, reusable=off |
| `TELEGRAM_BOT_TOKEN` | worker (Phase 3) | @BotFather in Telegram |
| `TELEGRAM_CHAT_ID` | worker (Phase 3) | @userinfobot in Telegram |

## Verification Results

All 9 verification checks passed:

1. `__init__.py` count: 8 (>= 5 required)
2. Dockerfile FROM stages: 4 (base, web, worker, beat)
3. `tailscaled --tun=userspace-networking` present in start-worker.sh
4. `FERNET_KEY: SecretStr` present in config.py
5. `.env` line present in `.gitignore`
6. CHANGE_ME occurrences in .env.example: 3 (>= 2 required)
7. No `backend/.env` file with real credentials
8. `test_no_secrets.py` exists
9. `test_vpn_health.py` exists

## Commits

| Task | Commit | Description |
|------|--------|-------------|
| Task 1 | a46e4a1 | feat(01-01): scaffold monorepo and multi-stage Dockerfile with Tailscale |
| Task 2 | edffe2a | feat(01-01): add pydantic-settings config, railway.toml, and .env.example |

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

The following items are intentional stubs to be wired in future plans:

| Stub | File | Reason |
|------|------|--------|
| `app.tasks.maintenance` import | `backend/app/celery_app.py` | Module does not exist yet; Celery will warn at startup but not crash. Created in Phase 2. |
| Empty `beat_schedule={}` | `backend/app/celery_app.py` | Schedule tasks added in Phase 2+ (polling, cleanup). |

## Threat Flags

No new security surface introduced beyond what was planned in the threat model.

All T-1-0x threats are mitigated:
- T-1-01: `.gitignore` excludes `.env`; `.env.example` uses CHANGE_ME; `test_no_secrets.py` in CI
- T-1-02: `FERNET_KEY` and `SECRET_KEY` are `SecretStr`
- T-1-03: `TAILSCALE_AUTH_KEY` documented as ephemeral key in `.env.example`
- T-1-04: Tailscale version pinning deferred (accepted risk)
- T-1-05: `start-worker.sh` echo statements do not print any secret variables
- T-1-06: Tailscale SaaS outage risk accepted

## Self-Check: PASSED

All files verified to exist and all commits confirmed in git log.
