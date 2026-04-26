---
phase: 01-infrastructure
plan: "02"
subsystem: database
tags: [postgresql, sqlalchemy, alembic, fernet, security, models]
dependency_graph:
  requires: ["01-01"]
  provides: ["database-schema", "fernet-encryption", "async-orm"]
  affects: ["02-polling", "03-alerts", "04-olts", "05-ubiquiti"]
tech_stack:
  added:
    - SQLAlchemy 2.0 async with mapped_column typed API
    - asyncpg driver (postgresql+asyncpg:// prefix)
    - Alembic async mode (async_engine_from_config)
    - cryptography.fernet for credential encryption
    - pytest + pytest-asyncio + pytest-timeout
  patterns:
    - "DeclarativeBase with Mapped[T] typed columns"
    - "async_sessionmaker with expire_on_commit=False"
    - "BRIN index on timestamp columns (plain PostgreSQL, no extensions)"
    - "Fernet symmetric encryption via SecretStr.get_secret_value()"
    - "monkeypatch env vars in conftest for unit tests without real DB"
key_files:
  created:
    - backend/app/models/base.py
    - backend/app/models/device.py
    - backend/app/models/metric.py
    - backend/app/models/alert.py
    - backend/app/models/incident.py
    - backend/app/models/onu.py
    - backend/app/models/device_credential.py
    - backend/app/models/__init__.py
    - backend/app/core/database.py
    - backend/app/core/security.py
    - backend/alembic.ini
    - backend/alembic/env.py
    - backend/alembic/script.py.mako
    - backend/alembic/versions/001_initial_schema.py
    - backend/pytest.ini
    - backend/tests/unit/conftest.py
    - backend/tests/unit/test_security.py
    - backend/tests/unit/test_db.py
  modified: []
decisions:
  - "[01-02]: PostgreSQL pure (no TimescaleDB) — metrics table uses BRIN index on recorded_at instead of hypertable"
  - "[01-02]: Alembic runs as Railway pre-deploy command (not container startup) to avoid blocking the app boot"
  - "[01-02]: FERNET_KEY is SecretStr — .get_secret_value() used in security.py, never logged"
metrics:
  duration: "~25 minutes"
  completed_date: "2026-04-26"
  tasks_completed: 2
  files_created: 18
---

# Phase 1 Plan 02: Database Schema, Alembic Async, and Fernet Encryption Summary

**One-liner:** PostgreSQL schema (6 tables, BRIN index) with SQLAlchemy 2.0 async ORM, Alembic async migrations, and Fernet credential encryption — 10/10 unit tests passing without real DB.

## What Was Built

### 6 SQLAlchemy Models (backend/app/models/)

| Model | Table | Key Columns | Indexes |
|-------|-------|-------------|---------|
| Device | devices | id, name, ip_address, device_type (enum), site, status (enum), is_active, consecutive_failures, last_seen_at, parent_device_id, pon_port | idx_devices_status, idx_devices_site, idx_devices_type, idx_devices_active |
| DeviceCredential | device_credentials | id, device_id (FK), credential_type, username, encrypted_password, encrypted_api_key, port | idx_device_credentials_unique (device_id + credential_type, UNIQUE) |
| Metric | metrics | id, device_id (FK), metric_name, value (Numeric 12,4), unit, interface, recorded_at | idx_metrics_device_recorded (device_id + recorded_at DESC), idx_metrics_recorded_at_brin (BRIN) |
| Alert | alerts | id, device_id (FK nullable), alert_type, threshold_value, is_active, consecutive_polls_required | none |
| Incident | incidents | id, device_id (FK), started_at, resolved_at, duration_seconds, cause, alert_sent, recovery_alert_sent | idx_incidents_active (partial: resolved_at IS NULL), idx_incidents_started (started_at DESC) |
| ONU | onus | id, device_id (FK), olt_id (FK nullable), serial_number, pon_port, signal_rx_dbm, signal_tx_dbm, onu_status, last_updated_at | idx_onus_olt, idx_onus_device |

### Exported Interfaces

**backend/app/core/security.py:**
```python
def encrypt_credential(plaintext: str) -> str:
    """Encripta credencial de equipo para almacenar en DB. Retorna string base64 cifrado."""

def decrypt_credential(ciphertext: str) -> str:
    """Desencripta credencial de equipo recuperada de DB. Retorna string plaintext."""
```

**backend/app/core/database.py:**
```python
engine: AsyncEngine          # postgresql+asyncpg://, pool_size=10, max_overflow=20, pool_pre_ping=True
AsyncSessionLocal: async_sessionmaker[AsyncSession]

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency for injecting async PostgreSQL session."""

def _build_async_url(raw_url: str) -> str:
    """Converts postgresql:// to postgresql+asyncpg://"""
```

**backend/app/models/base.py:**
```python
class Base(DeclarativeBase):
    pass
```

### Alembic Async Configuration

- **alembic.ini**: `sqlalchemy.url =` (empty — URL set in env.py from settings to avoid hardcoding credentials)
- **alembic/env.py**: Uses `async_engine_from_config` + `asyncio.run(run_migrations_online())` — not the default sync engine
- **alembic/versions/001_initial_schema.py**: Creates all 6 tables with indexes; `downgrade()` drops all tables in reverse order

### Railway Migration Command

```bash
cd backend && alembic upgrade head
```

Configure as Railway pre-deploy command (not container startup). Required environment variable: `DATABASE_URL`.

### Unit Test Results

```
platform win32 -- Python 3.14.3, pytest-9.0.3
10 passed in 0.45s
```

Tests run without PostgreSQL or Redis (conftest.py injects test env vars via monkeypatch):

| Test | File | What It Verifies |
|------|------|-----------------|
| test_fernet_roundtrip | test_security.py | encrypt + decrypt returns original plaintext |
| test_fernet_ciphertext_not_plaintext | test_security.py | ciphertext != plaintext (DEPLOY-03) |
| test_fernet_different_plaintexts_different_ciphertexts | test_security.py | different inputs produce different outputs |
| test_fernet_invalid_token_raises | test_security.py | InvalidToken raised on bad ciphertext |
| test_fernet_empty_string_roundtrip | test_security.py | empty string encrypts/decrypts correctly |
| test_all_required_tablenames_exist | test_db.py | 6 correct tablenames present |
| test_device_credential_uses_encrypted_fields | test_db.py | encrypted_password and encrypted_api_key, no plaintext "password" field |
| test_device_status_enum_values | test_db.py | up, down, warning, unknown |
| test_device_type_enum_has_all_required_types | test_db.py | all 7 device types present |
| test_database_url_conversion | test_db.py | postgresql:// → postgresql+asyncpg:// |

## Decisions Made

1. **PostgreSQL pure, no TimescaleDB**: metrics.recorded_at uses BRIN index (Block Range INdex) — available in standard PostgreSQL without extensions. TimescaleDB hypertable creation intentionally excluded. Data retention via Celery beat task (Phase 2).

2. **Alembic as pre-deploy command**: Migrations run before container starts (`alembic upgrade head` in Railway pre-deploy). Not called at application startup to avoid blocking the FastAPI boot.

3. **FERNET_KEY as SecretStr**: `settings.FERNET_KEY.get_secret_value()` used in `_get_fernet()`. The key is never logged or str()-cast.

4. **idx_device_credentials_unique**: Unique composite index on (device_id, credential_type) ensures one credential record per type per device.

## Deviations from Plan

None — plan executed exactly as written.

The only notable observation: the migration file contains "TimescaleDB" in comments (explaining the decision not to use it), which is expected and correct. No `create_hypertable` calls exist in the file.

## Known Stubs

None — all 6 models are fully defined with proper column types and constraints.

## Threat Flags

None — no new network endpoints, auth paths, or trust boundaries introduced. This plan only creates database schema definitions and a local encryption utility.

## Verification Results

All 9 verification checks from the plan passed:

1. security.py syntax: OK
2. encrypted fields count: 3 (encrypted_password, encrypted_api_key x2 occurrences)
3. async_engine_from_config import: present
4. asyncio.run call: present
5. postgresql_using="brin": present
6. create_hypertable count: 0
7. pytest 10 passed: confirmed
8. tablenames count: 6
9. testpaths = tests/unit: confirmed

## Self-Check: PASSED

All files confirmed to exist:
- backend/app/models/base.py: FOUND
- backend/app/models/device.py: FOUND
- backend/app/models/metric.py: FOUND
- backend/app/models/alert.py: FOUND
- backend/app/models/incident.py: FOUND
- backend/app/models/onu.py: FOUND
- backend/app/models/device_credential.py: FOUND
- backend/app/core/database.py: FOUND
- backend/app/core/security.py: FOUND
- backend/alembic.ini: FOUND
- backend/alembic/env.py: FOUND
- backend/alembic/versions/001_initial_schema.py: FOUND
- backend/pytest.ini: FOUND
- backend/tests/unit/conftest.py: FOUND
- backend/tests/unit/test_security.py: FOUND
- backend/tests/unit/test_db.py: FOUND

Commits:
- f2329fd: feat(01-02): SQLAlchemy models, async database engine, and Alembic async setup
- cbb7a37: feat(01-02): Fernet security module and unit tests (TDD green — 10/10 passed)
