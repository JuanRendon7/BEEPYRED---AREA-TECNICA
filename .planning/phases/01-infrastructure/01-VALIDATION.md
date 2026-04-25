---
phase: 1
slug: infrastructure
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-25
---

# Phase 1 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x |
| **Config file** | `backend/pytest.ini` (Wave 0 installs) |
| **Quick run command** | `cd backend && pytest tests/unit/ -q` |
| **Full suite command** | `cd backend && pytest tests/ -v` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `cd backend && pytest tests/unit/ -q`
- **After every plan wave:** Run `cd backend && pytest tests/ -v`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 1-01-01 | 01 | 1 | INFRA-01 | T-1-01 | VPN conecta Railway a red privada ISP | manual | `railway run python -c "import subprocess; subprocess.run(['ping','-c1','<ISP_HOST>'])"` | ❌ W0 | ⬜ pending |
| 1-01-02 | 01 | 1 | INFRA-02 | — | PostgreSQL externo accesible, sin almacenamiento local | unit | `pytest tests/unit/test_db.py -q` | ❌ W0 | ⬜ pending |
| 1-01-03 | 01 | 1 | INFRA-03 | T-1-02 | Ninguna credencial hardcodeada en código | unit | `pytest tests/unit/test_no_secrets.py -q` | ❌ W0 | ⬜ pending |
| 1-02-01 | 02 | 1 | DEPLOY-01 | — | Servicios web+worker+beat despliegan sin errores | manual | `railway status` | ❌ W0 | ⬜ pending |
| 1-02-02 | 02 | 2 | DEPLOY-03 | T-1-03 | Credenciales de equipos encriptadas con Fernet en DB | unit | `pytest tests/unit/test_encryption.py -q` | ❌ W0 | ⬜ pending |
| 1-03-01 | 03 | 1 | INFRA-02 | — | Schema inicial creado con Alembic, sin storage efímero | unit | `pytest tests/unit/test_schema.py -q` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `backend/tests/__init__.py` — init package de tests
- [ ] `backend/tests/unit/__init__.py` — init tests unitarios
- [ ] `backend/tests/unit/test_db.py` — stub: verifica conexión PostgreSQL y que no usa SQLite
- [ ] `backend/tests/unit/test_no_secrets.py` — stub: escanea archivos Python por secrets hardcodeados (regex de IPs, passwords, tokens)
- [ ] `backend/tests/unit/test_encryption.py` — stub: verifica encrypt/decrypt con Fernet produce bytes distintos del plaintext
- [ ] `backend/tests/unit/test_schema.py` — stub: verifica que tablas `devices`, `device_credentials`, `metrics`, `alerts`, `incidents`, `onus` existen en la DB

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Worker Railway puede hacer ping a equipo ISP | INFRA-01 | Requiere acceso real a Railway y a la red ISP privada | 1. Deploy worker en Railway, 2. `railway run python -c "import os; os.system('ping -c1 <ISP_IP>')"`, 3. Verificar respuesta ICMP |
| Servicios web+worker+beat despliegan en Railway | DEPLOY-01 | Requiere Railway account y token configurado | `railway up`, verificar en dashboard Railway que 3 servicios están activos |
| Variables de entorno no están en el código | INFRA-03 | Parcialmente automatizable, pero verificación final es visual | Revisar `git log -p` que ningún commit contiene valores reales de credenciales |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
