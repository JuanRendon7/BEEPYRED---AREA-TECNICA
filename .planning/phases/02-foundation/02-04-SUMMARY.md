---
phase: 02-foundation
plan: "04"
subsystem: frontend + sse
tags: [react, vite, shadcn, sse, jwt, tanstack-query, react-router]
dependency_graph:
  requires: [02-01, 02-02, 02-03]
  provides: [POLL-04, POLL-05]
  affects: [frontend-all]
tech_stack:
  added:
    - React 19 + TypeScript 6 (Vite 8 scaffold)
    - shadcn/ui v4 (base-ui/react primitivos, no radix)
    - TanStack Query v5
    - React Router v6
    - Axios 1.7
    - Tailwind CSS v3 + PostCSS
  patterns:
    - SSE via EventSource con token JWT en query param (EventSource no soporta headers)
    - StreamingResponse FastAPI con text/event-stream
    - TanStack Query cache update optimista desde SSE (sin refetch)
    - PrivateRoute guard via localStorage token check
    - OAuth2PasswordRequestForm con application/x-www-form-urlencoded
key_files:
  created:
    - backend/app/api/events.py
    - frontend/src/api/client.ts
    - frontend/src/hooks/useDeviceStream.ts
    - frontend/src/router.tsx
    - frontend/src/pages/Login.tsx
    - frontend/src/pages/Dashboard.tsx
    - frontend/src/pages/Inventory.tsx
    - frontend/src/components/DeviceCard.tsx
    - frontend/src/components/InventoryForm.tsx
  modified:
    - backend/app/main.py (events_router incluido)
    - frontend/src/App.tsx (QueryClientProvider + AppRouter)
    - frontend/src/main.tsx (StrictMode entry point)
    - frontend/tsconfig.app.json (alias @/*, ignoreDeprecations 6.0)
    - frontend/tsconfig.json (paths en raiz para shadcn init)
    - frontend/vite.config.ts (alias @ y proxy /api)
    - frontend/src/index.css (variables CSS shadcn/ui oklch)
    - frontend/tailwind.config.js (content paths + colores CSS vars)
decisions:
  - "shadcn v4 usa @base-ui/react en lugar de @radix-ui — API de primitivos ligeramente diferente pero variantes (default/destructive/outline/secondary) compatibles con el plan"
  - "TypeScript 6 depreco baseUrl — se agrego ignoreDeprecations=6.0 en tsconfig.app.json para mantener alias @ funcional"
  - "frontend/dist/ excluido de git (.gitignore) — Railway hace build en deploy"
  - "Warnings lightningcss de @theme/@utility de tw-animate-css son inofensivos — build exitoso sin errores"
metrics:
  duration: "~45 minutos"
  completed_date: "2026-04-27"
  tasks_completed: 3
  files_created: 13
  files_modified: 7
---

# Phase 02 Plan 04: SSE endpoint + React Frontend Summary

SSE FastAPI endpoint con validacion JWT manual via query param + scaffold Vite React 19 + shadcn/ui v4 + login/dashboard/inventory CRUD con actualizacion en tiempo real via EventSource.

## Objective

Cerrar el ciclo POLL-05 completo: polling worker actualiza DB y Redis; SSE lleva el estado al browser; el tecnico ve UP/DOWN/WARNING/UNKNOWN sin recargar la pagina.

## What Was Built

### Backend — GET /events SSE endpoint

**Archivo:** `backend/app/api/events.py`

- `StreamingResponse` con `media_type="text/event-stream"`
- Validacion JWT manual via `_validate_sse_token(token)` — retorna 401 sin token valido
- Token recibido como query param `?token=...` (EventSource del browser no soporta headers Authorization)
- Suscripcion a Redis pub/sub canal `device_status` con cleanup al desconectar
- Keep-alive inicial `":\n\n"` para confirmar conexion al browser
- Headers: `Cache-Control: no-cache`, `X-Accel-Buffering: no`, `Connection: keep-alive`
- Mitigaciones T-2-32 (validacion JWT) y T-2-33 (request.is_disconnected()) implementadas

**Endpoint:** `GET /events?token=<jwt>`

### Frontend — React 19 + Vite 8 + shadcn/ui v4

**Scaffold:**
- `npm create vite@latest` con template `react-ts`
- TypeScript 6, React 19, Vite 8
- shadcn/ui v4.5.0 (usa `@base-ui/react` en lugar de `@radix-ui`)
- Componentes instalados: button, card, input, label, badge, table, dialog
- Tailwind CSS v3 + PostCSS + Autoprefixer
- Alias `@/*` → `./src/*` en tsconfig.app.json y tsconfig.json
- Proxy Vite: `/api/...` → `http://localhost:8000/...`

**Archivos creados:**

| Archivo | Descripcion |
|---------|-------------|
| `src/api/client.ts` | axios instance, JWT interceptor, tipos Device/DeviceCreate |
| `src/hooks/useDeviceStream.ts` | EventSource SSE → actualiza TanStack Query cache optimistamente |
| `src/router.tsx` | React Router v6 + PrivateRoute guard |
| `src/pages/Login.tsx` | OAuth2 form-urlencoded, JWT → localStorage → redirect /dashboard |
| `src/pages/Dashboard.tsx` | Grid DeviceCards, resumen UP/DOWN/WARNING, SSE activo |
| `src/pages/Inventory.tsx` | Tabla CRUD, mutaciones create/update/delete |
| `src/components/DeviceCard.tsx` | Badge de estado con variantes default/destructive/secondary/outline |
| `src/components/InventoryForm.tsx` | Dialog modal para crear y editar equipos |

## Verification Results

```
# Backend sintaxis OK
python -m py_compile app/api/events.py → OK

# Backend unit tests — sin regresiones
python -m pytest tests/unit/ -q → 51 passed in 1.02s

# Frontend build
npm run build → ✓ built in 700ms
dist/index.html + dist/assets/ generados correctamente
```

## SSE Architecture Note

**Limitacion EventSource + JWT (decision T-2-30 aceptada):**

El browser `EventSource` no soporta headers custom como `Authorization: Bearer ...`. Para v1 (herramienta interna, usuario unico):

- Token pasado como query param: `GET /events?token=eyJ...`
- Visible en logs del servidor Railway (aceptado para v1)
- Mitigacion T-2-32: endpoint valida JWT manualmente con `jwt.decode()` antes de iniciar el stream
- Si se requiere auditoria estricta en v2: migrar a cookie httpOnly

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Bloqueante] Tailwind CSS no instalado antes de shadcn init**
- **Encontrado durante:** Tarea 2a
- **Issue:** `npx shadcn@latest init --defaults` fallo con "No Tailwind CSS configuration found"
- **Fix:** Instalar `tailwindcss@3 postcss autoprefixer`, ejecutar `npx tailwindcss init -p`, configurar `tailwind.config.js` con content paths antes de `shadcn init`
- **Archivos modificados:** `frontend/tailwind.config.js`, `frontend/postcss.config.js`
- **Commit:** `63a8be7`

**2. [Rule 3 - Bloqueante] shadcn init busca alias en tsconfig.json raiz, no en tsconfig.app.json**
- **Encontrado durante:** Tarea 2a
- **Issue:** shadcn v4 lee `tsconfig.json` raiz para validar el alias `@/*`; solo tenia el alias en `tsconfig.app.json`
- **Fix:** Agregar `compilerOptions.paths` en `tsconfig.json` raiz tambien
- **Archivos modificados:** `frontend/tsconfig.json`
- **Commit:** `63a8be7`

**3. [Rule 1 - Bug] TypeScript 6 depreco la opcion baseUrl**
- **Encontrado durante:** Tarea 2b (npm run build)
- **Issue:** `tsconfig.app.json(23,5): error TS5101: Option 'baseUrl' is deprecated in TypeScript 7.0. Specify "ignoreDeprecations": "6.0"` — build fallaba
- **Fix:** Agregar `"ignoreDeprecations": "6.0"` en `tsconfig.app.json`
- **Archivos modificados:** `frontend/tsconfig.app.json`
- **Commit:** `2301e11`

**4. [Observacion] shadcn v4 usa @base-ui/react en lugar de @radix-ui**
- **Encontrado durante:** Inspeccion de componentes instalados
- **Impacto:** API de Dialog es `DialogPrimitive.Root.Props` con `open`/`onOpenChange` — compatible con el plan. Button usa `ButtonPrimitive.Props` que extiende props HTML estandar. No requirio cambios en el codigo del plan.

## Known Stubs

Ninguno. Todos los componentes estan conectados a la API real via `apiClient`.

## Self-Check: PASSED

| Item | Status |
|------|--------|
| backend/app/api/events.py | FOUND |
| frontend/src/api/client.ts | FOUND |
| frontend/src/hooks/useDeviceStream.ts | FOUND |
| frontend/src/router.tsx | FOUND |
| frontend/src/pages/Login.tsx | FOUND |
| frontend/src/pages/Dashboard.tsx | FOUND |
| frontend/src/pages/Inventory.tsx | FOUND |
| frontend/src/components/DeviceCard.tsx | FOUND |
| frontend/src/components/InventoryForm.tsx | FOUND |
| commit 92a9459 | FOUND |
| commit 63a8be7 | FOUND |
| commit 2301e11 | FOUND |
