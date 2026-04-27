---
phase: 02-foundation
plan: 01
subsystem: auth
tags: [jwt, auth, security, fastapi, pyjwt, pwdlib, argon2]
dependency_graph:
  requires: [01-02]
  provides: [CurrentUser, create_access_token, JWT-auth-endpoints]
  affects: [02-02, 02-03, 02-04]
tech_stack:
  added: [pyjwt[crypto]>=2.10.1, pwdlib[argon2]==0.2.1, python-multipart==0.0.20]
  patterns: [OAuth2PasswordBearer, Argon2-via-pwdlib, timing-attack-mitigation]
key_files:
  created:
    - backend/app/models/user.py
    - backend/app/core/auth.py
    - backend/app/api/auth.py
    - backend/app/api/deps.py
    - backend/alembic/versions/002_add_users_table.py
    - backend/scripts/seed_admin.py
    - backend/tests/unit/test_auth.py
  modified:
    - backend/requirements.txt
    - backend/app/core/config.py
    - backend/app/main.py
    - backend/tests/unit/conftest.py
    - .env.example
decisions:
  - "PyJWT upgraded to >=2.10.1 (from 2.9.0) to resolve conflict with mcp>=2.10.1 on dev machine"
  - "ADMIN_PASSWORD default 'changeme' accepted — seed_admin.py guards production deploy"
  - "Timing attack mitigation via _DUMMY_HASH in POST /auth/login — prevents user enumeration"
  - "CORS configured with explicit origins list (no wildcard) — allow_credentials=True requires this"
metrics:
  duration: 5m
  completed_date: "2026-04-27"
  tasks_completed: 2
  files_created: 7
  files_modified: 5
---

# Phase 02 Plan 01: JWT Auth Backend Summary

**One-liner:** JWT auth con PyJWT+pwdlib/Argon2, timing-attack mitigation, CurrentUser dependency para proteger todos los endpoints de Phase 2+.

## What Was Built

Autenticacion JWT completa para BEEPYRED NOC:

- **User model** (`backend/app/models/user.py`): tabla `users` con `id`, `username` (unique), `hashed_password`, `is_active`, `created_at`
- **Auth core** (`backend/app/core/auth.py`): `create_access_token`, `password_hash` (Argon2), `get_current_user`, `get_current_active_user`
- **Auth router** (`backend/app/api/auth.py`): `POST /auth/login` con timing-attack mitigation via `_DUMMY_HASH`, `GET /auth/me`
- **Deps** (`backend/app/api/deps.py`): `CurrentUser = Annotated[User, Depends(get_current_active_user)]` — alias para proteger rutas
- **Migration 002** (`backend/alembic/versions/002_add_users_table.py`): `CREATE TABLE users` con unique index en username
- **Seed script** (`backend/scripts/seed_admin.py`): crea usuario admin desde `ADMIN_USERNAME`/`ADMIN_PASSWORD`, rechaza `"changeme"` en produccion
- **main.py**: router montado en `/auth`, CORS con origenes explícitos (sin wildcard)

## Interfaces Exported

```python
# backend/app/core/auth.py
create_access_token(sub: str, expires_delta: timedelta | None = None) -> str
password_hash: PasswordHash  # Argon2 via pwdlib
get_current_active_user(current_user: User) -> User  # FastAPI Depends

# backend/app/api/deps.py
CurrentUser = Annotated[User, Depends(get_current_active_user)]

# backend/app/api/auth.py
router: APIRouter  # prefix="/auth", tags=["auth"]
# POST /auth/login -> {"access_token": str, "token_type": "bearer"}
# GET  /auth/me   -> {"id": int, "username": str, "is_active": bool}
```

## Test Results

```
tests/unit/test_auth.py — 10 passed
tests/unit/ (total)     — 28 passed, 0 failed
```

Tests cubiertos:
- `test_create_access_token_returns_decodable_jwt` — AUTH-01/02
- `test_token_expiry_raises` — AUTH-02
- `test_verify_password_correct` — AUTH-01
- `test_verify_password_wrong` — AUTH-01
- `test_user_model_tablename` — modelo
- `test_user_model_has_required_fields` — modelo
- `test_user_username_is_unique` — constraint
- `test_access_token_expire_minutes_setting` — AUTH-02
- `test_algorithm_is_hs256` — seguridad
- `test_oauth2_scheme_token_url` — OpenAPI docs

## Commits

| Hash | Tarea | Descripcion |
|------|-------|-------------|
| `6f8373c` | Tarea 1 | JWT auth core — User model, PyJWT+pwdlib, Alembic 002, 10 unit tests |
| `0b143f5` | Tarea 2 | Auth router, deps.py CurrentUser, seed_admin, CORS, .env.example |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] PyJWT version bumped from 2.9.0 to >=2.10.1**
- **Found during:** Tarea 1 — instalacion de dependencias
- **Issue:** `mcp 1.26.0` en el entorno dev requiere `pyjwt[crypto]>=2.10.1`. Instalar `pyjwt==2.9.0` causaba conflicto de dependencias.
- **Fix:** Cambiar `pyjwt==2.9.0` a `pyjwt[crypto]>=2.10.1` en requirements.txt. La API de PyJWT es compatible entre 2.9 y 2.12 — ningún cambio en auth.py.
- **Files modified:** `backend/requirements.txt`
- **Commit:** `6f8373c`

**2. [Rule 1 - Bug] .env.example TAILSCALE_AUTH_KEY placeholder activaba regex detector**
- **Found during:** Tarea 1 — ejecucion de suite completa de tests
- **Issue:** `test_env_example_uses_placeholders` en `test_no_secrets.py` detectaba `tskey-auth-CHANGE_ME` como posible key real (el regex `tskey-auth-[A-Za-z0-9]+` coincide con el texto del placeholder).
- **Fix:** Cambiar placeholder a `CHANGE_ME_tskey_auth_key_from_tailscale_admin` (no empieza con `tskey-auth-`).
- **Files modified:** `.env.example`
- **Commit:** `6f8373c`

**3. [Rule 3 - Blocking] python-multipart agregado a requirements.txt**
- **Found during:** Tarea 2 — analisis de dependencias de OAuth2PasswordRequestForm
- **Issue:** FastAPI requiere `python-multipart` para procesar form data (usado por `OAuth2PasswordRequestForm` en `POST /auth/login`). Sin este paquete el endpoint falla en runtime.
- **Fix:** Agregar `python-multipart==0.0.20` a requirements.txt.
- **Files modified:** `backend/requirements.txt`
- **Commit:** `6f8373c`

## Threat Model Coverage

Todas las mitigaciones del threat register implementadas:

| Threat ID | Mitigation | Status |
|-----------|-----------|--------|
| T-2-01 | Argon2 via pwdlib + _DUMMY_HASH timing mitigation | Implementado |
| T-2-02 | jwt.decode() con SECRET_KEY + algorithms=["HS256"] | Implementado |
| T-2-03 | CurrentUser dependency en deps.py para todos los routers | Implementado |
| T-2-04 | JWT payload solo contiene sub+exp (aceptado) | Aceptado |
| T-2-05 | _DUMMY_HASH path: respuesta identica para user inexistente | Implementado |
| T-2-06 | Rate limiting diferido a v2 (aceptado) | Aceptado |
| T-2-07 | SecretStr.get_secret_value() solo en auth.py, no loggeado | Implementado |

## Known Stubs

Ninguno — todos los endpoints retornan datos reales. El seed script requiere DB real para ejecutarse (diseño intencional).

## Self-Check: PASSED

| Check | Result |
|-------|--------|
| backend/app/models/user.py | FOUND |
| backend/app/core/auth.py | FOUND |
| backend/app/api/auth.py | FOUND |
| backend/app/api/deps.py | FOUND |
| backend/alembic/versions/002_add_users_table.py | FOUND |
| backend/scripts/seed_admin.py | FOUND |
| backend/tests/unit/test_auth.py | FOUND |
| commit 6f8373c | FOUND |
| commit 0b143f5 | FOUND |
| 28 tests passing | CONFIRMED |
