---
phase: 02-foundation
plan: "02"
subsystem: inventory
tags: [pydantic, fastapi, crud, devices, inventory]
dependency_graph:
  requires: [02-01]
  provides: [DeviceCreate, DeviceUpdate, DeviceRead, router-devices]
  affects: [02-03-polling, 02-04-sse]
tech_stack:
  added: []
  patterns: [pydantic-v2-field-validator, sqlalchemy-orm-async-crud, soft-delete]
key_files:
  created:
    - backend/app/schemas/__init__.py
    - backend/app/schemas/device.py
    - backend/app/api/devices.py
    - backend/tests/unit/test_inventory.py
  modified:
    - backend/app/main.py
decisions:
  - "DeviceUpdate excluye campo status — solo el worker de polling puede cambiarlo (T-2-12)"
  - "DELETE soft delete (is_active=False) preserva historial para auditoria (T-2-14)"
  - "GET /devices?active_only=true por defecto — oculta equipos eliminados del listado"
metrics:
  duration: "2m"
  completed_date: "2026-04-27"
  tasks_completed: 2
  files_created: 4
  files_modified: 1
---

# Phase 02 Plan 02: Device Inventory CRUD Backend Summary

**One-liner:** CRUD completo /devices con 5 endpoints JWT-protegidos, schemas Pydantic v2 con validacion IPvAnyAddress y soft delete.

## Objective

Implementar el inventario de equipos de red como fuente de verdad para el ciclo de polling (Plan 03). Sin este CRUD, el worker no tiene dispositivos que monitorear.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Schemas Pydantic v2 + 12 tests TDD | 57e97df | backend/app/schemas/device.py, backend/tests/unit/test_inventory.py |
| 2 | Router CRUD /devices + montaje en main.py | b55bdd7 | backend/app/api/devices.py, backend/app/main.py |

## Endpoints Created

| Metodo | Ruta | Descripcion | Status code |
|--------|------|-------------|-------------|
| GET | /devices | Lista equipos activos (filtro `?site=X`, `?active_only=true`) | 200 |
| POST | /devices | Crear equipo nuevo (estado inicial UNKNOWN) | 201 |
| GET | /devices/{id} | Obtener equipo por ID | 200 / 404 |
| PUT | /devices/{id} | Actualizar campos del equipo | 200 / 404 |
| DELETE | /devices/{id} | Soft delete (is_active=False) | 204 / 404 |

Todos los endpoints requieren Bearer token valido (CurrentUser dependency — AUTH-03).

## Schemas Exportados

| Schema | Uso | Campos clave |
|--------|-----|--------------|
| `DeviceCreate` | Input POST /devices | name (requerido), ip_address (validado), device_type (enum), site (opcional) |
| `DeviceUpdate` | Input PUT /devices/{id} | Todos opcionales — PATCH semantics |
| `DeviceRead` | Response de todos los endpoints | id, status, is_active, consecutive_failures, from_attributes=True |

## Validaciones Implementadas

- **IP address:** `IPvAnyAddress` de Pydantic v2 valida IPv4 e IPv6. IPs invalidas (ej. `999.999.999.999`) retornan `ValidationError` antes de tocar la DB (T-2-10).
- **Nombre no vacio:** `field_validator` rechaza strings vacios o solo espacios en DeviceCreate y DeviceUpdate.
- **DeviceType enum:** Solo acepta los 7 tipos definidos en el modelo: mikrotik, olt_vsol_gpon, olt_vsol_epon, onu, ubiquiti, mimosa, other.
- **Status protegido:** `DeviceUpdate` no expone campo `status` — solo el worker de polling puede cambiarlo (T-2-12).

## Resultado de pytest

```
tests/unit/test_inventory.py — 12 passed
tests/unit/ (suite completa) — 40 passed, 0 failed
```

## Deviations from Plan

None — plan ejecutado exactamente como estaba escrito.

## Known Stubs

None — no hay datos hardcodeados ni placeholders que fluyan a la UI.

## Threat Flags

None — todos los endpoints protegidos por CurrentUser, validacion IP en schema, soft delete preserva historial. Ver threat model en el PLAN.md para detalle completo.

## Self-Check: PASSED

- FOUND: backend/app/schemas/device.py
- FOUND: backend/app/schemas/__init__.py
- FOUND: backend/app/api/devices.py
- FOUND: backend/tests/unit/test_inventory.py
- FOUND commit: 57e97df (schemas + tests)
- FOUND commit: b55bdd7 (router + main.py)
