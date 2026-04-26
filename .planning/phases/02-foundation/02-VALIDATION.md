---
phase: 2
slug: foundation
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-26
---

# Phase 2 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework backend** | pytest 8.3.5 + pytest-asyncio 0.25.3 |
| **Framework frontend** | vitest (via Vite) |
| **Config file** | backend/pytest.ini (exists) |
| **Quick run command** | `cd backend && python -m pytest tests/unit/ -q` |
| **Full suite command** | `cd backend && python -m pytest tests/ -q` |
| **Estimated runtime** | ~5 seconds (unit) / ~15 seconds (integration) |

---

## Sampling Rate

- **After every task commit:** Run `cd backend && python -m pytest tests/unit/ -q`
- **After every plan wave:** Run `cd backend && python -m pytest tests/ -q`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|--------|
| 2-01-01 | 01 | 1 | AUTH-01 | T-2-01 | POST /auth/token rechaza password incorrecto con 401 | unit | `pytest tests/unit/test_auth.py -q` | ⬜ pending |
| 2-01-02 | 01 | 1 | AUTH-02 | T-2-02 | Token JWT invalido/expirado rechazado con 401 | unit | `pytest tests/unit/test_auth.py::test_invalid_token -q` | ⬜ pending |
| 2-01-03 | 01 | 1 | AUTH-03 | T-2-03 | Endpoints protegidos devuelven 401 sin Bearer token | unit | `pytest tests/unit/test_auth.py::test_protected_requires_auth -q` | ⬜ pending |
| 2-02-01 | 02 | 1 | INV-01 | — | POST /devices crea equipo con campos requeridos | unit | `pytest tests/unit/test_inventory.py::test_create_device -q` | ⬜ pending |
| 2-02-02 | 02 | 1 | INV-02 | — | PUT /devices/{id} actualiza equipo; DELETE elimina | unit | `pytest tests/unit/test_inventory.py::test_update_delete -q` | ⬜ pending |
| 2-02-03 | 02 | 1 | INV-03 | — | GET /devices agrupa por site correctamente | unit | `pytest tests/unit/test_inventory.py::test_list_by_site -q` | ⬜ pending |
| 2-02-04 | 02 | 1 | INV-04 | T-2-04 | Credenciales almacenadas cifradas Fernet (no plaintext) | unit | `pytest tests/unit/test_inventory.py::test_credentials_encrypted -q` | ⬜ pending |
| 2-03-01 | 03 | 2 | POLL-01 | — | Task Celery ejecuta ping a lista de IPs con semaforo 50 | unit | `pytest tests/unit/test_polling.py::test_semaphore_limit -q` | ⬜ pending |
| 2-03-02 | 03 | 2 | POLL-02 | — | Poll marca equipo DOWN solo tras 3 fallos consecutivos | unit | `pytest tests/unit/test_polling.py::test_consecutive_failures -q` | ⬜ pending |
| 2-03-03 | 03 | 2 | POLL-03 | — | Timeout individual por equipo respetado (no bloquea ciclo) | unit | `pytest tests/unit/test_polling.py::test_timeout_isolation -q` | ⬜ pending |
| 2-03-04 | 03 | 2 | POLL-04 | — | Redis pub/sub publica evento status_changed en cada cambio | unit | `pytest tests/unit/test_polling.py::test_redis_pubsub -q` | ⬜ pending |
| 2-04-01 | 04 | 2 | POLL-05 | — | SSE endpoint /events transmite eventos al cliente | manual | curl -N -H "Authorization: Bearer {token}" http://localhost:8000/api/v1/events | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `backend/tests/unit/test_auth.py` — stubs para AUTH-01, AUTH-02, AUTH-03
- [ ] `backend/tests/unit/test_inventory.py` — stubs para INV-01..04
- [ ] `backend/tests/unit/test_polling.py` — stubs para POLL-01..05
- [ ] `backend/tests/unit/conftest.py` — actualizar con fixtures de auth (test_user, auth_headers)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| SSE stream en browser | POLL-05 | Requiere browser real o curl streaming | `curl -N -H "Authorization: Bearer {token}" http://localhost:8000/api/v1/events` — verificar que llegan eventos `data: {...}` |
| Dashboard UP/DOWN en tiempo real | POLL-05 | Requiere UI corriendo | Abrir dashboard, agregar equipo, apagar dispositivo, verificar que status cambia a DOWN tras 3 polls (~3 min) |
| Login persiste entre visitas | AUTH-01 | Requiere browser con cookies/localStorage | Iniciar sesion, cerrar pestaña, reabrir — verificar que no pide login de nuevo |

---

## Validation Architecture (from RESEARCH.md)

| Success Criterion | Test Type | Tool | Expected Outcome |
|-------------------|-----------|------|-----------------|
| JWT auth flow — login y token valido | unit | pytest + PyJWT | POST /auth/token retorna access_token; token decodificable con SECRET_KEY |
| ICMP ping con semaforo concurrencia 50 | unit | pytest + unittest.mock (mock subprocess) | Semaphore(50) limita coroutines concurrentes; mock ping retorna (0=UP, 1=DOWN) |
| SSE event stream | manual + curl | curl -N streaming | Endpoint /events retorna Content-Type: text/event-stream; eventos llegan cada poll |
| Logica 3 fallos consecutivos | unit | pytest | consecutive_failures se incrementa en fallo, reset en exito; DOWN solo al llegar a 3 |
| CRUD inventario | unit | pytest + TestClient | POST/GET/PUT/DELETE /devices retornan 201/200/200/204 con datos correctos |
