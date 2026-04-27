---
phase: 02-foundation
verified: 2026-04-27T04:00:00Z
status: human_needed
score: 5/5 must-haves verificados
overrides_applied: 0
human_verification:
  - test: "Abrir /login en el navegador, ingresar credenciales incorrectas y verificar que muestra error. Ingresar credenciales correctas, verificar redirect a /dashboard y que el JWT queda en localStorage."
    expected: "Login fallido muestra 'Usuario o contrasena incorrectos'. Login exitoso redirige a /dashboard. La sesion persiste al recargar la pagina."
    why_human: "Requiere servidor corriendo, usuario admin sembrado en DB, y verificacion visual de la UI y del comportamiento de almacenamiento del token."
  - test: "En /inventory, crear un equipo con nombre, IP, tipo 'mikrotik' y sitio 'Torre Norte'. Verificar que aparece en la tabla. Editarlo cambiando el sitio. Eliminarlo."
    expected: "El equipo aparece inmediatamente en la tabla tras crearlo. La edicion actualiza los datos mostrados. La eliminacion remueve el equipo de la lista."
    why_human: "Requiere DB corriendo con datos reales y verificacion visual del ciclo CRUD completo en la pagina /inventory."
  - test: "Con al menos un equipo en el inventario y el worker Celery corriendo, esperar 60 segundos y verificar que el estado UP/DOWN del equipo cambia en /dashboard sin recargar la pagina."
    expected: "El estado del equipo se actualiza en tiempo real. La conexion SSE permanece abierta (verificar en DevTools > Network > EventStream). Los cambios de estado de DOWN ocurren solo despues de 3 polls fallidos consecutivos."
    why_human: "Requiere worker Celery + Redis + PostgreSQL corriendo simultáneamente. La logica de debounce (3 fallos) tarda al menos 3 ciclos de 60s = 3 minutos para observarse."
---

# Phase 2: Foundation — Reporte de Verificacion

**Objetivo de la fase:** El tecnico puede iniciar sesion, registrar equipos en el inventario, y ver en tiempo real cuales estan UP y cuales DOWN — sin necesidad de metricas ricas, solo ICMP ping.
**Verificado:** 2026-04-27T04:00:00Z
**Estado:** human_needed
**Re-verificacion:** No — verificacion inicial

---

## Logro del Objetivo

### Verdades Observables

| # | Verdad | Estado | Evidencia |
|---|--------|--------|-----------|
| 1 | El tecnico puede iniciar sesion con usuario y contrasena y la sesion persiste (JWT); sin autenticacion la plataforma es inaccesible | VERIFICADO | `POST /auth/login` existe en `backend/app/api/auth.py` con logica completa (PyJWT + Argon2). `GET /auth/me` protegido por `CurrentUser`. `PrivateRoute` en `frontend/src/router.tsx` redirige a `/login` sin token. JWT guardado en `localStorage` en `Login.tsx`. |
| 2 | El tecnico puede agregar, editar y eliminar equipos con nombre, IP, tipo y sitio, y agruparlos por sitio geografico | VERIFICADO | 5 endpoints CRUD en `backend/app/api/devices.py`. `GET /devices?site=X` implementado. Soft delete (`is_active=False`). Pagina `/inventory` con tabla, formulario y mutaciones TanStack Query. |
| 3 | El sistema ejecuta ICMP ping a todos los equipos cada 60 segundos con concurrencia limitada a 50 simultaneos y timeout individual | VERIFICADO | `polling.py` usa `asyncio.Semaphore(settings.MAX_CONCURRENT_CONNECTIONS)` (50). `asyncio.wait_for(timeout=DEVICE_TIMEOUT_SECONDS)`. Beat schedule `poll-all-devices` con `schedule=settings.POLL_INTERVAL_SECONDS` (60s) en `celery_app.py`. |
| 4 | Un equipo aparece como DOWN solo despues de 3 polls consecutivos fallidos | VERIFICADO | Logica en `_ping_and_update()`: `dev.consecutive_failures += 1` en cada fallo; `dev.status = DeviceStatus.DOWN` solo cuando `>= settings.CONSECUTIVE_FAILURES_THRESHOLD` (3). Reset a 0 en exito. Test `test_consecutive_failures_down_at_threshold` confirma el comportamiento. |
| 5 | El estado UP/DOWN se actualiza en el dashboard sin recargar la pagina (Server-Sent Events) | VERIFICADO | `GET /events?token=...` en `backend/app/api/events.py` retorna `StreamingResponse` con `media_type="text/event-stream"`. Hook `useDeviceStream.ts` conecta via `EventSource` y actualiza el cache de TanStack Query optimistamente. Dashboard llama `useDeviceStream()`. |

**Puntuacion:** 5/5 verdades verificadas

---

### Artefactos Requeridos

| Artefacto | Descripcion | Estado | Detalles |
|-----------|-------------|--------|---------|
| `backend/app/models/user.py` | Modelo SQLAlchemy User (tabla users) | VERIFICADO | `class User`, columnas id/username/hashed_password/is_active/created_at, `__tablename__ = "users"` |
| `backend/app/core/auth.py` | create_access_token, get_current_active_user, password_hash | VERIFICADO | PyJWT (`import jwt`), `PasswordHash.recommended()` (Argon2), `OAuth2PasswordBearer` |
| `backend/app/api/auth.py` | Router /auth con login y /auth/me | VERIFICADO | `@router.post("/login")` y `@router.get("/me")` implementados, timing attack mitigation con `_DUMMY_HASH` |
| `backend/app/api/deps.py` | CurrentUser como dependencia Annotated | VERIFICADO | `CurrentUser = Annotated[User, Depends(get_current_active_user)]` |
| `backend/alembic/versions/002_add_users_table.py` | Migracion CREATE TABLE users | VERIFICADO | `op.create_table("users", ...)` con indice unico en username |
| `backend/scripts/seed_admin.py` | Script de seed usuario admin | VERIFICADO | Lee `ADMIN_USERNAME`/`ADMIN_PASSWORD` de Settings, guarda usuario con hash Argon2, valida que no sea "changeme" |
| `backend/tests/unit/test_auth.py` | Tests AUTH-01/02/03 | VERIFICADO | 10 tests cubriendo login valido, expiracion, verificacion de password, modelo User |
| `backend/app/schemas/device.py` | DeviceCreate, DeviceUpdate, DeviceRead | VERIFICADO | IPvAnyAddress para validacion IP, `from_attributes=True` en DeviceRead, DeviceUpdate totalmente opcional |
| `backend/app/api/devices.py` | Router CRUD /devices | VERIFICADO | 5 endpoints GET/POST/PUT/DELETE con CurrentUser, soft delete, filtro por sitio |
| `backend/tests/unit/test_inventory.py` | Tests INV-01/02/03/04 | VERIFICADO | 11 tests de schemas Pydantic |
| `backend/app/tasks/polling.py` | Task Celery poll_all_devices + ping_host + consecutive_failures | VERIFICADO | `asyncio.Semaphore`, `asyncio.wait_for`, logica debounce 3 fallos, Redis pub/sub canal `device_status` |
| `backend/app/celery_app.py` | Beat schedule poll-all-devices 60s | VERIFICADO | `beat_schedule["poll-all-devices"]` con `schedule=settings.POLL_INTERVAL_SECONDS`, `expires` anti-acumulacion |
| `backend/tests/unit/test_polling.py` | Tests POLL-01/02/03/04/05 | VERIFICADO | 11 tests cubriendo ping_host, semaforo, consecutive_failures, Redis pub/sub, beat schedule |
| `backend/app/api/events.py` | SSE GET /events | VERIFICADO | `StreamingResponse` con `text/event-stream`, validacion JWT antes del stream, suscripcion Redis pubsub `device_status` |
| `frontend/src/api/client.ts` | Axios instance con JWT interceptor | VERIFICADO | Interceptor de request agrega `Authorization: Bearer <token>`, interceptor de response maneja 401 |
| `frontend/src/hooks/useDeviceStream.ts` | Hook SSE conectado a /api/events | VERIFICADO | `EventSource(/api/events?token=...)`, actualiza cache TanStack Query con `setQueryData` |
| `frontend/src/pages/Login.tsx` | Pagina login | VERIFICADO | Formulario usuario/contrasena, `URLSearchParams` para OAuth2 form-encoded, guarda token en `localStorage` |
| `frontend/src/pages/Dashboard.tsx` | Dashboard con tarjetas de equipos | VERIFICADO | TanStack Query `["devices"]`, `DeviceCard` por equipo, contador UP/DOWN/WARNING, llama `useDeviceStream()` |
| `frontend/src/pages/Inventory.tsx` | Inventario CRUD | VERIFICADO | Tabla con datos reales de DB, formulario via `InventoryForm`, mutaciones create/update/delete |
| `frontend/src/router.tsx` | PrivateRoute guard | VERIFICADO | `PrivateRoute` verifica `localStorage.getItem("token")`, redirige a `/login` si ausente |

---

### Verificacion de Enlazado Clave

| Desde | Hacia | Via | Estado | Detalles |
|-------|-------|-----|--------|---------|
| `backend/app/api/auth.py` | `backend/app/core/auth.py` | `from app.core.auth import create_access_token, get_user_by_username, password_hash` | VERIFICADO | Import confirmado en auth.py linea 19 |
| `backend/app/main.py` | `backend/app/api/auth.py` | `app.include_router(auth_router.router)` | VERIFICADO | main.py linea 26 |
| `backend/app/main.py` | `backend/app/api/devices.py` | `app.include_router(devices_router.router)` | VERIFICADO | main.py linea 27 |
| `backend/app/main.py` | `backend/app/api/events.py` | `app.include_router(events_router.router)` | VERIFICADO | main.py linea 28 |
| `backend/app/api/devices.py` | `backend/app/api/deps.py` | `from app.api.deps import CurrentUser` | VERIFICADO | devices.py linea 18 |
| `backend/app/tasks/polling.py` | `redis.asyncio` | `r.publish("device_status", json.dumps({...}))` | VERIFICADO | polling.py linea 133 |
| `backend/app/celery_app.py` | `backend/app/tasks/polling.py` | `include=["app.tasks.polling"]`, `"task": "tasks.poll_all_devices"` | VERIFICADO | celery_app.py lineas 11, 24 |
| `frontend/src/pages/Dashboard.tsx` | `frontend/src/hooks/useDeviceStream.ts` | `useDeviceStream()` llamado en DashboardPage | VERIFICADO | Dashboard.tsx linea 30 |
| `frontend/src/hooks/useDeviceStream.ts` | `GET /api/events` | `new EventSource(/api/events?token=...)` | VERIFICADO | useDeviceStream.ts linea 29 |

---

### Flujo de Datos (Nivel 4)

| Artefacto | Variable de datos | Fuente | Produce datos reales | Estado |
|-----------|------------------|--------|----------------------|--------|
| `Dashboard.tsx` | `devices` | `GET /api/devices` via TanStack Query | Si — consulta DB PostgreSQL via SQLAlchemy `select(Device).where(is_active=True)` | FLOWING |
| `Dashboard.tsx` (SSE) | cache `["devices"]` | `useDeviceStream` via `EventSource /api/events` | Si — Redis pubsub recibe eventos del worker Celery cuando el estado cambia | FLOWING |
| `Inventory.tsx` | `devices` | `GET /api/devices` via TanStack Query | Si — misma consulta DB | FLOWING |
| `events.py` | `message["data"]` | Redis pubsub canal `device_status` | Si — publicado por `publish_status_update()` en `polling.py` cuando el estado cambia | FLOWING |

---

### Verificacion Comportamental (Spot-checks)

| Comportamiento | Comando | Resultado | Estado |
|---------------|---------|-----------|--------|
| Suite de tests backend | `cd backend && python -m pytest tests/unit/ -q` | 51 passed in 1.17s | PASS |
| Frontend compila | `cd frontend && npm run build` | `dist/index.html` generado, `✓ built in 652ms` | PASS |
| Module celery beat schedule | `python -c "from app.celery_app import celery_app; assert 'poll-all-devices' in celery_app.conf.beat_schedule"` | OK (verificado por test_beat_schedule_has_poll_all_devices) | PASS |
| Router devices importa | Verificado via test suite sin errores de import | 51 tests pasan incluyendo tests de inventario | PASS |
| SSE endpoint | Requiere servidor corriendo | N/A | SKIP (requiere servidor) |

---

### Cobertura de Requerimientos

| Requerimiento | Plan | Descripcion | Estado | Evidencia |
|--------------|------|-------------|--------|-----------|
| AUTH-01 | 02-01 | Login con credenciales validas retorna JWT | SATISFECHO | `POST /auth/login` en auth.py, 10 tests pasan |
| AUTH-02 | 02-01 | JWT expira segun ACCESS_TOKEN_EXPIRE_MINUTES | SATISFECHO | `timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)`, test_token_expiry_raises pasa |
| AUTH-03 | 02-01 | GET /auth/me requiere Bearer token valido | SATISFECHO | `CurrentUser` dependency en get_me |
| INV-01 | 02-02 | POST /devices crea equipo con validacion | SATISFECHO | DeviceCreate con IPvAnyAddress, endpoint 201 |
| INV-02 | 02-02 | GET /devices?site=X filtra por sitio | SATISFECHO | `stmt.where(Device.site == site)` en list_devices |
| INV-03 | 02-02 | PUT/DELETE actualizan/eliminan equipo | SATISFECHO | update_device con model_dump(exclude_unset=True), soft delete |
| INV-04 | 02-02 | GET /devices retorna estado actual UP/DOWN | SATISFECHO | DeviceRead incluye campo `status` de DB |
| POLL-01 | 02-03 | Polling cada 60s via Celery beat | SATISFECHO | beat_schedule schedule=POLL_INTERVAL_SECONDS=60 |
| POLL-02 | 02-03 | Concurrencia maxima 50 con Semaphore | SATISFECHO | `asyncio.Semaphore(settings.MAX_CONCURRENT_CONNECTIONS)` = 50 |
| POLL-03 | 02-03 | DOWN tras 3 fallos consecutivos | SATISFECHO | `if dev.consecutive_failures >= CONSECUTIVE_FAILURES_THRESHOLD: dev.status = DeviceStatus.DOWN` |
| POLL-04 | 02-03 | Cambios de estado a Redis canal device_status | SATISFECHO | `publish_status_update()` publica `{"id", "status"}` al canal `"device_status"` |
| POLL-05 | 02-04 | SSE actualiza dashboard sin recargar | SATISFECHO | EventSource en useDeviceStream.ts, StreamingResponse en events.py |

---

### Anti-Patrones Encontrados

| Archivo | Linea | Patron | Severidad | Impacto |
|---------|-------|--------|-----------|---------|
| `backend/app/models/user.py` | 19 | `default=datetime.utcnow` (utcnow deprecado en Python 3.12+) | Info | Cosmético — funciona pero genera DeprecationWarning. La alternativa es `datetime.now(timezone.utc)`. No afecta la funcionalidad. |
| `frontend/build output` | N/A | Warnings CSS de `@theme`/`@utility` de Tailwind v4 en lightningcss | Info | Solo advertencias CSS del minificador — no son errores. El build completa exitosamente y el CSS se genera correctamente. |

No se encontraron: TODOs/FIXMEs criticos, componentes placeholder, rutas sin implementacion, estados hardcodeados, o handlers vacios.

---

### Verificacion Humana Requerida

#### 1. Flujo de autenticacion completo (AUTH-01, AUTH-02, AUTH-03)

**Prueba:** Navegar a `http://localhost:5173`, verificar redirect a `/login`. Intentar login con credenciales incorrectas. Intentar con credenciales correctas (requiere `seed_admin.py` ejecutado previamente).
**Esperado:** Acceso rechazado sin credenciales validas. Login exitoso redirige a `/dashboard`. Token JWT en `localStorage`. Al recargar la pagina, el tecnico sigue logueado (sesion persistente). Al cerrar sesion y navegar a `/inventory`, redirige a `/login`.
**Por que humano:** Requiere servidor FastAPI corriendo, PostgreSQL con schema migrado, usuario admin sembrado via `seed_admin.py`, y verificacion visual del comportamiento de sesion.

#### 2. CRUD completo de inventario (INV-01, INV-02, INV-03, INV-04)

**Prueba:** En `/inventory`, crear equipos con distintos sitios geograficos (ej: "Torre Norte", "Nodo Centro"). Verificar agrupacion visual. Editar un equipo. Eliminar un equipo y verificar que desaparece. Verificar que el equipo eliminado no aparece en el conteo.
**Esperado:** Creacion con 201, tabla actualiza inmediatamente. Edicion refleja cambios. Eliminacion remueve de la vista. El filtro por sitio en `/inventory` funciona.
**Por que humano:** Requiere DB PostgreSQL con datos y verificacion visual de la tabla y el formulario `InventoryForm`.

#### 3. Actualizacion en tiempo real via SSE (POLL-03, POLL-04, POLL-05)

**Prueba:** Con Celery worker + Redis corriendo, agregar un equipo con IP inaccesible (ej: `192.0.2.1`). Esperar 3 ciclos de 60s (3 minutos). Verificar que aparece como DOWN en el dashboard sin recargar la pagina.
**Esperado:** El equipo comienza como UNKNOWN. Despues de 3 polls fallidos (3 minutos), la tarjeta cambia a DOWN en el dashboard en tiempo real via SSE. En DevTools > Network, la conexion a `/api/events` permanece abierta y recibe el evento de cambio de estado.
**Por que humano:** Requiere Celery worker + Redis + PostgreSQL activos. La logica de debounce (3 fallos) tarda minutos en observarse. Requiere verificacion de la conexion SSE en DevTools del navegador.

---

## Resumen de Brechas

No se encontraron brechas de implementacion. Todos los criterios de exito del ROADMAP estan implementados en codigo con pruebas automatizadas pasando (51/51 tests, build frontend exitoso).

Los 3 items de verificacion humana son comportamientos end-to-end que requieren infraestructura corriendo (PostgreSQL, Redis, Celery) y verificacion visual — no pueden verificarse con herramientas estaticas de codigo.

---

_Verificado: 2026-04-27T04:00:00Z_
_Verificador: Claude (gsd-verifier)_
