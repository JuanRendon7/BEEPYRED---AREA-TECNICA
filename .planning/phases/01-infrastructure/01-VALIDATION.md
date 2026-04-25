---
phase: 1
slug: infrastructure
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-25
revised: 2026-04-25
---

# Phase 1 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x |
| **Config file** | `backend/pytest.ini` (Plan 02, Task 2) |
| **Quick run command** | `cd backend && pytest tests/unit/ -q` |
| **Full suite command** | `cd backend && pytest tests/unit/ -v` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `cd backend && pytest tests/unit/ -q`
- **After every plan wave:** Run `cd backend && pytest tests/unit/ -v`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 1-01-01 | 01 | 1 | INFRA-01 | T-1-01 | VPN conecta Railway a red privada ISP via Tailscale userspace | unit+manual | `pytest tests/unit/test_vpn_health.py -q` (unit); `railway run python -c "import subprocess; subprocess.run(['ping','-c1','<ISP_HOST>'])"` (manual) | ❌ W0 | ⬜ pending |
| 1-01-02 | 01 | 1 | INFRA-03 | T-1-02 | Ninguna credencial hardcodeada en código | unit | `pytest tests/unit/test_no_secrets.py -q` | ❌ W0 | ⬜ pending |
| 1-02-01 | 02 | 1 | INFRA-02 | — | PostgreSQL externo accesible, schema correcto, sin almacenamiento local | unit | `pytest tests/unit/test_db.py -q` | ❌ W0 | ⬜ pending |
| 1-02-02 | 02 | 1 | DEPLOY-03 | T-1-07 | Credenciales de equipos encriptadas con Fernet en DB | unit | `pytest tests/unit/test_security.py -q` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `backend/tests/__init__.py` — init package de tests (creado en Plan 01, Task 1)
- [ ] `backend/tests/unit/__init__.py` — init tests unitarios (creado en Plan 01, Task 1)
- [ ] `backend/tests/unit/test_vpn_health.py` — stub INFRA-01: verifica directivas Tailscale en start-worker.sh y Dockerfile (creado en Plan 01, Task 1)
- [ ] `backend/tests/unit/test_no_secrets.py` — stub INFRA-03: escanea archivos Python por secrets hardcodeados (creado en Plan 01, Task 1)
- [ ] `backend/tests/unit/conftest.py` — fixtures con monkeypatch para DATABASE_URL, FERNET_KEY, etc. (creado en Plan 02, Task 2)
- [ ] `backend/tests/unit/test_security.py` — tests Fernet roundtrip, ciphertext != plaintext, invalid token raises (creado en Plan 02, Task 2)
- [ ] `backend/tests/unit/test_db.py` — tests de tablenames, encrypted fields, enum values, URL conversion (creado en Plan 02, Task 2)
- [ ] `backend/pytest.ini` — config con `testpaths = tests/unit`, `asyncio_mode = auto` (creado en Plan 02, Task 2)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Worker Railway puede hacer ping a equipo ISP via Tailscale | INFRA-01 | Requiere acceso real a Railway y a la red ISP privada | 1. Deploy worker en Railway, 2. `railway run python -c "import os; os.system('ping -c1 <ISP_IP>')"`, 3. Verificar respuesta ICMP. El Mikrotik debe estar configurado como subnet router Tailscale antes del test. |
| Servicios web+worker+beat despliegan en Railway | DEPLOY-01 | Requiere Railway account y token configurado | `railway up`, verificar en dashboard Railway que 3 servicios están activos |
| Variables de entorno no están en el código | INFRA-03 | Parcialmente automatizado por test_no_secrets.py; verificación final es visual | Revisar `git log -p` que ningún commit contiene valores reales de credenciales. Complementa el test automatizado. |
| Migraciones Alembic aplican correctamente en Railway | INFRA-02 | Requiere Railway PostgreSQL addon activo | Configurar DATABASE_URL en Railway, ejecutar `railway run alembic upgrade head`, verificar tablas en Railway DB console |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
