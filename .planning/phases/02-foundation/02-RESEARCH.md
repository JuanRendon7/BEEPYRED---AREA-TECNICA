# Phase 2: Foundation — Research

**Researched:** 2026-04-26
**Domain:** FastAPI Auth (JWT) + CRUD API + Async ICMP Polling + SSE + React Frontend
**Confidence:** HIGH (stack verified via official docs and PyPI registry)

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| AUTH-01 | Tecnico puede iniciar sesion con usuario y contrasena | FastAPI OAuth2PasswordBearer + PyJWT + pwdlib + seed user en DB |
| AUTH-02 | Sesion persiste entre visitas (JWT con expiracion configurable) | PyJWT `ACCESS_TOKEN_EXPIRE_MINUTES` configurable via settings; token almacenado en memoria React + localStorage como fallback |
| AUTH-03 | Plataforma inaccesible sin autenticacion (rutas protegidas) | `get_current_active_user` Depends en todos los routers; React Router guard |
| INV-01 | Registrar equipo: nombre, IP, tipo, sitio, estado inicial | Modelo Device ya existe en Phase 1; agregar router CRUD + Pydantic schemas |
| INV-02 | Agrupar equipos por sitio geografico | Campo `site` ya en Device model; endpoint `GET /devices?group_by=site` |
| INV-03 | Agregar, editar y eliminar equipos | CRUD completo: POST /devices, PUT /devices/{id}, DELETE /devices/{id} |
| INV-04 | Inventario muestra estado actual UP/DOWN/WARNING/UNKNOWN en tiempo real | Estado leido de DB actualizado por Celery worker; SSE empuja cambios al browser |
| POLL-01 | ICMP ping a todos los equipos cada 60 segundos | Celery beat task cada 60s; asyncio.create_subprocess_exec para ping |
| POLL-02 | Concurrencia limitada a 50 simultaneos | asyncio.Semaphore(50) en el event loop del task Celery |
| POLL-03 | DOWN solo tras 3 polls consecutivos fallidos | `consecutive_failures` en Device model (ya existe); incrementar en cada fallo, reset a 0 en exito |
| POLL-04 | Estado UP/DOWN actualizado sin recargar pagina | SSE via FastAPI 0.135+ `EventSourceResponse`; Celery publica a Redis pub/sub |
| POLL-05 | Timeout individual por equipo sin bloquear ciclo | `asyncio.wait_for(..., timeout=DEVICE_TIMEOUT_SECONDS)` alrededor de cada ping subprocess |
</phase_requirements>

---

## Summary

Phase 2 construye la columna vertebral operacional del NOC: autenticacion JWT, inventario CRUD, y el primer ciclo de polling real. La arquitectura sigue el patron ya establecido en Phase 1: FastAPI (web) + Celery (worker) + Redis (broker/pubsub) + PostgreSQL (estado persistente).

El reto tecnico principal de esta fase es el ICMP en Railway: los contenedores de Railway no tienen `NET_RAW` capability, lo que impide raw sockets. La solucion confirmada por Railway es usar `iputils-ping` instalado via apt — la version moderna usa ICMP datagram sockets que no requieren `NET_RAW`. El worker invoca `ping` via `asyncio.create_subprocess_exec` con `asyncio.wait_for` para timeout, coordinado con `asyncio.Semaphore(50)` para limitar concurrencia.

Para JWT, FastAPI 0.135+ recomienda `PyJWT` + `pwdlib[argon2]`. `python-jose` esta abandonado y es incompatible con Python 3.13+. `passlib` esta sin mantenimiento. La nueva dupla oficial es PyJWT + pwdlib con Argon2. El frontend React (Vite + TS + shadcn/ui + TanStack Query) se inicializa desde cero en esta fase — no existe aun en el repo.

**Primary recommendation:** ICMP via subprocess `ping` (iputils-ping en Dockerfile) + `asyncio.Semaphore` + Celery beat; JWT via PyJWT + pwdlib; SSE via `fastapi.sse.EventSourceResponse` (nativo desde 0.135.0 — ya instalado en el stack).

---

## Project Constraints (from CLAUDE.md)

- Deploy en Railway — contenedores sin `NET_ADMIN` ni `NET_RAW` por defecto
- Python 3.12, FastAPI, Celery+Redis, PostgreSQL 16 asyncpg ya instalados
- React 18 + Vite + TS + shadcn/ui + TanStack Query — frontend por inicializar
- Usuario unico v1 — sin sistema de registro; usuario inicial creado por seed script
- POLL_INTERVAL_SECONDS=60, MAX_CONCURRENT_CONNECTIONS=50, DEVICE_TIMEOUT_SECONDS=10 ya en Settings
- CONSECUTIVE_FAILURES_THRESHOLD=3 ya en Settings
- SECRET_KEY ya como SecretStr en Settings — lista para firmar JWT
- `consecutive_failures` ya en Device model — usar este campo, no Redis counter separado

---

## Standard Stack

### Core (Phase 2 additions to requirements.txt)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| PyJWT | 2.9+ | JWT encoding/decoding | Reemplazo oficial de python-jose en FastAPI docs desde May 2024; mantenido activamente |
| pwdlib[argon2] | 0.2+ | Password hashing | Recomendacion actual de FastAPI docs; Argon2 es memory-hard, resistente a GPU brute-force |
| sse-starlette | 2.x / OR fastapi.sse | Server-Sent Events | Incluido en FastAPI 0.135+ como `fastapi.sse.EventSourceResponse` — sin dependencia adicional |

**Version verification:** [VERIFIED: PyPI npm view equivalent]
- `PyJWT` latest stable: 2.9.0 (2024) — instalar `pyjwt`
- `pwdlib[argon2]` latest: 0.2.1 — instalar `pwdlib[argon2]`
- `fastapi.sse.EventSourceResponse` disponible desde FastAPI 0.135.0 — ya instalado como 0.136.1

**CRITICO — python-jose NO usar:** `python-jose` esta abandonado (ultimo release ~3 años atras), incompatible con Python ≥3.13, y retirado de la documentacion oficial de FastAPI. [VERIFIED: github.com/fastapi/fastapi/discussions/11345]

**CRITICO — passlib NO usar:** `passlib` no tiene mantenimiento; el modulo `crypt` que usa fue removido en Python 3.13. [VERIFIED: github.com/fastapi/fastapi/discussions/11773]

### Frontend (inicializar desde cero en frontend/)

| Library | Version | Purpose | Why |
|---------|---------|---------|-----|
| React | 18.3+ | UI framework | Definido en CLAUDE.md/stack |
| Vite | 6.x | Build tool | Definido en stack; shadcn CLI lo requiere |
| TypeScript | 5.4+ | Type safety | Definido en stack |
| shadcn/ui | latest (CLI) | Componentes UI | Copia componentes al repo; no dependency lock |
| Tailwind CSS | 4.x (nuevo) | Utility CSS | shadcn init configura automaticamente |
| TanStack Query | 5.x | Server state | Definido en stack; maneja polling REST |
| React Router | 6.x | Routing SPA | Rutas: /login, /dashboard, /inventory |
| axios | 1.7+ | HTTP client | Interceptors para JWT bearer token en headers |

**Instalacion frontend:**
```bash
npm create vite@latest frontend -- --template react-ts
cd frontend
npm install
npm install @tanstack/react-query react-router-dom axios
npm install -D @types/node
npx shadcn@latest init
npx shadcn@latest add button card input label badge table dialog form
```

**Instalacion backend (agregar a requirements.txt):**
```bash
pyjwt
pwdlib[argon2]
```

**NOTA iputils-ping en Dockerfile:** Agregar al stage `base`:
```dockerfile
RUN apt-get update && apt-get install -y --no-install-recommends iputils-ping && rm -rf /var/lib/apt/lists/*
```

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| subprocess ping (iputils-ping) | icmplib async_ping | icmplib requiere NET_RAW o CAP_NET_RAW — Railway no lo da; subprocess ping con iputils funciona sin ese cap |
| PyJWT + pwdlib | python-jose + passlib | python-jose abandonado; passlib sin mantenimiento; PyJWT+pwdlib es la pila actual de FastAPI docs |
| fastapi.sse nativo | sse-starlette | fastapi.sse nativo (0.135+) es suficiente; sse-starlette es alternativa valida si se necesitan features extra |
| Device.consecutive_failures (DB) | Redis INCR counter | Redis counter es efimero — si el worker se reinicia se pierde el conteo; DB column persiste reinicios |
| localStorage para JWT | httpOnly cookie | httpOnly cookie es mas seguro contra XSS; para herramienta interna con un solo tecnico localStorage es aceptable; httpOnly requiere configurar cookie handling en CORS y frontend |

---

## Architecture Patterns

### Recommended Project Structure (Phase 2 additions)

```
backend/
├── app/
│   ├── api/
│   │   ├── auth.py          # POST /auth/login, GET /auth/me
│   │   ├── devices.py       # CRUD /devices, GET /devices/stream (SSE)
│   │   └── deps.py          # get_current_user dependency
│   ├── schemas/
│   │   ├── auth.py          # Token, TokenData, LoginRequest
│   │   └── device.py        # DeviceCreate, DeviceUpdate, DeviceRead
│   ├── tasks/
│   │   └── polling.py       # poll_all_devices Celery task
│   └── core/
│       └── auth.py          # create_access_token, verify_password, seed_user
frontend/
├── src/
│   ├── api/
│   │   └── client.ts        # axios instance con JWT interceptor
│   ├── components/
│   │   ├── ui/              # shadcn components (auto-generados)
│   │   └── DeviceCard.tsx   # tarjeta UP/DOWN con badge
│   ├── pages/
│   │   ├── Login.tsx        # pagina de login
│   │   ├── Dashboard.tsx    # vista principal SSE
│   │   └── Inventory.tsx    # CRUD equipos
│   ├── hooks/
│   │   └── useDeviceStream.ts  # EventSource hook para SSE
│   └── router.tsx           # React Router con PrivateRoute guard
```

### Pattern 1: JWT Auth — PyJWT + pwdlib (FastAPI official pattern)

```python
# Source: https://fastapi.tiangolo.com/tutorial/security/oauth2-jwt/
import jwt
from pwdlib import PasswordHash
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi import Depends, HTTPException, status

ALGORITHM = "HS256"
password_hash = PasswordHash.recommended()  # Argon2 por defecto
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=30))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.SECRET_KEY.get_secret_value(), algorithm=ALGORITHM)

async def get_current_user(token: str = Depends(oauth2_scheme), db: AsyncSession = Depends(get_db)):
    try:
        payload = jwt.decode(token, settings.SECRET_KEY.get_secret_value(), algorithms=[ALGORITHM])
        username = payload.get("sub")
        if username is None:
            raise credentials_exception
    except jwt.InvalidTokenError:
        raise credentials_exception
    # query user from DB by username
    ...
```

**Seed user approach:** Un script `backend/scripts/seed_admin.py` crea el usuario tecnico al primer deploy. No hay endpoint de registro publico (AUTH-03). El script lee `ADMIN_USERNAME` y `ADMIN_PASSWORD` de env vars.

### Pattern 2: ICMP Polling — subprocess ping con asyncio.Semaphore

```python
# Source: Railway docs + Python asyncio docs
# iputils-ping instalado en Dockerfile — usa ICMP datagram socket, no requiere NET_RAW
import asyncio

_semaphore = asyncio.Semaphore(settings.MAX_CONCURRENT_CONNECTIONS)  # 50

async def ping_host(ip: str, timeout: int) -> bool:
    """Retorna True si host responde al ping."""
    async with _semaphore:
        try:
            proc = await asyncio.create_subprocess_exec(
                "ping", "-c", "1", "-W", str(timeout), ip,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await asyncio.wait_for(proc.wait(), timeout=timeout + 1)
            return proc.returncode == 0
        except (asyncio.TimeoutError, OSError):
            if proc:
                proc.kill()
            return False

async def poll_all_devices_async(device_list: list) -> None:
    tasks = [ping_and_update(device) for device in device_list]
    await asyncio.gather(*tasks, return_exceptions=True)
```

**CRITICO — Celery + asyncio bridge:** Celery workers usan el event loop de manera sincrónica. El patron correcto es `asyncio.run()` dentro del task sincrónico:

```python
# Source: [VERIFIED: Celery docs + Python asyncio docs]
@celery_app.task(name="tasks.poll_all_devices")
def poll_all_devices():
    """Celery task sincronico que ejecuta el ciclo de ping async."""
    asyncio.run(_poll_all_devices_async())

async def _poll_all_devices_async():
    # obtener devices de DB, hacer ping, actualizar consecutive_failures
    ...
```

**ADVERTENCIA:** No usar `loop.run_until_complete()` — deprecated. Usar `asyncio.run()` que crea un event loop limpio para cada invocacion del task.

### Pattern 3: consecutive_failures — DB column (ya existe)

```python
# Device.consecutive_failures: Mapped[int] en Phase 1
# Logica de debounce (POLL-03):

async def ping_and_update(device: Device, db: AsyncSession) -> None:
    is_up = await ping_host(device.ip_address, settings.DEVICE_TIMEOUT_SECONDS)

    if is_up:
        device.consecutive_failures = 0
        device.status = DeviceStatus.UP
        device.last_seen_at = datetime.now(timezone.utc)
    else:
        device.consecutive_failures += 1
        if device.consecutive_failures >= settings.CONSECUTIVE_FAILURES_THRESHOLD:
            device.status = DeviceStatus.DOWN

    await db.commit()
    # publicar cambio de estado a Redis para SSE
    await redis_client.publish("device_status", json.dumps({
        "id": device.id, "status": device.status
    }))
```

**Decision:** Usar `Device.consecutive_failures` (columna DB) en lugar de Redis counter. Razon: persiste reinicios del worker; CONSECUTIVE_FAILURES_THRESHOLD=3 ya en Settings; el modelo ya tiene el campo.

### Pattern 4: SSE — fastapi.sse nativo (FastAPI 0.135+)

```python
# Source: https://fastapi.tiangolo.com/tutorial/server-sent-events/
# FastAPI 0.136.1 ya instalado — EventSourceResponse disponible en fastapi.sse
from fastapi.sse import EventSourceResponse
from collections.abc import AsyncIterable
import redis.asyncio as aioredis

@router.get("/devices/stream", response_class=EventSourceResponse)
async def device_status_stream(
    current_user=Depends(get_current_active_user),
) -> AsyncIterable[dict]:
    r = aioredis.from_url(settings.REDIS_URL)
    pubsub = r.pubsub()
    await pubsub.subscribe("device_status")
    try:
        async for message in pubsub.listen():
            if message["type"] == "message":
                yield json.loads(message["data"])
    finally:
        await pubsub.unsubscribe("device_status")
        await r.aclose()
```

**Alternativa con sse-starlette:** Si se necesitan features extra (retry, named events, shutdown grace period), usar `sse-starlette` que tambien esta instalado (version 3.2.0 en el entorno de desarrollo). Para Phase 2 el nativo es suficiente.

### Pattern 5: Frontend — TanStack Query + React Router guard + SSE hook

```typescript
// src/hooks/useDeviceStream.ts
// Source: MDN EventSource API + TanStack Query pattern
import { useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";

export function useDeviceStream(token: string) {
  const queryClient = useQueryClient();

  useEffect(() => {
    // SSE no soporta custom headers — pasar token como query param
    const es = new EventSource(`/api/devices/stream?token=${token}`);
    es.onmessage = (event) => {
      const update = JSON.parse(event.data);
      // invalidar query de devices para que TanStack Query refresque
      queryClient.setQueryData(["devices"], (old: Device[]) =>
        old?.map(d => d.id === update.id ? { ...d, status: update.status } : d)
      );
    };
    return () => es.close();
  }, [token, queryClient]);
}
```

**CRITICO — EventSource y JWT:** `EventSource` del browser no soporta headers custom. Opciones:
1. Pasar token como query param `?token=...` — valido para herramienta interna
2. Usar cookie httpOnly — mas seguro pero requiere mas configuracion CORS
Para v1 (usuario unico, herramienta interna), query param es aceptable. [ASSUMED]

### Pattern 6: Vite dev proxy para desarrollo

```typescript
// vite.config.ts — evita CORS en desarrollo local
export default defineConfig({
  server: {
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },
});
```

En produccion (Railway), el frontend compilado se sirve como archivos estaticos desde FastAPI con `StaticFiles` o desde un servicio Nginx separado. Para Phase 2 usar `StaticFiles` en FastAPI para minimizar servicios Railway.

### Anti-Patterns to Avoid

- **NO usar python-jose:** Abandonado, incompatible con Python 3.13+. Usar PyJWT.
- **NO usar passlib:** Sin mantenimiento, modulo `crypt` removido en 3.13. Usar pwdlib.
- **NO usar icmplib:** Requiere NET_RAW o root — Railway no los da. Usar subprocess + iputils-ping.
- **NO usar asyncio.get_event_loop().run_until_complete():** Deprecated en Python 3.10+. Usar asyncio.run().
- **NO almacenar consecutive_failures solo en Redis:** Se pierde si el worker se reinicia. Usar DB column (ya existe).
- **NO crear registration endpoint publico:** Usuario unico v1; solo seed script interno.
- **NO poner `allow_origins=["*"]` con `allow_credentials=True`:** CORS bloqueara la request. Especificar origen exacto.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| JWT encode/decode | Parser JWT manual | `PyJWT` (pyjwt) | Constante time comparison, algoritmos seguros, bien auditado |
| Password hashing | MD5/SHA256 directo | `pwdlib[argon2]` | Argon2 es memory-hard; bcrypt/MD5 son triviales con GPU |
| OAuth2 form extraction | Parsear form data | `OAuth2PasswordRequestForm` (FastAPI builtin) | Spec-compliant, maneja content-type correcto |
| ICMP raw sockets Python | Implementar ICMP manualmente | `subprocess ping` + `iputils-ping` | Raw sockets requieren NET_RAW; subprocess evita el problema |
| SSE frame formatting | Formatear `data: ...\n\n` manualmente | `fastapi.sse.EventSourceResponse` | Maneja encoding, keep-alive, reconexion automatica |
| Redis async pub/sub client | Implementar protocolo Redis | `redis.asyncio` (ya en redis==7.4.0) | Incluido en la lib ya instalada |
| Concurrent task limiting | Thread pool manual | `asyncio.Semaphore(50)` | Nativo de asyncio; cero overhead de threads |

**Key insight:** El stack de Phase 1 ya incluye `redis==7.4.0` que trae `redis.asyncio` — no hay que instalar `aioredis` ni ninguna lib adicional para pub/sub async.

---

## Common Pitfalls

### Pitfall 1: ICMP falla silenciosamente en Railway sin iputils-ping
**What goes wrong:** La imagen base de Python no incluye `ping`; el subprocess falla con `FileNotFoundError`; todos los equipos aparecen como DOWN.
**Why it happens:** `python:3.12-slim` no incluye herramientas de red.
**How to avoid:** Agregar `RUN apt-get install -y iputils-ping` en el stage `base` del Dockerfile. Verificar con test `assert shutil.which("ping") is not None`.
**Warning signs:** `returncode=-1` en todos los pings; error en logs del worker.

### Pitfall 2: asyncio.Semaphore no es thread-safe entre workers Celery
**What goes wrong:** Si se tienen multiples workers Celery en paralelo, el Semaphore de cada proceso es independiente — no hay coordinacion global. Resultado: se envian mas de 50 pings simultaneos si hay 2+ workers.
**Why it happens:** asyncio.Semaphore es por-proceso.
**How to avoid:** Configurar Celery para que solo un worker ejecute la tarea de polling. Usar `--concurrency=1` para el polling worker, o usar Celery `beat` con `max_instances=1`. [ASSUMED — necesita validacion con configuracion Railway]

### Pitfall 3: EventSource browser no puede enviar Authorization header
**What goes wrong:** El SSE endpoint requiere JWT pero EventSource no soporta headers custom; el browser obtiene 401 en la conexion SSE.
**Why it happens:** Limitacion del browser EventSource API (W3C spec).
**How to avoid:** Pasar token como query param `GET /devices/stream?token=...`; validar en el endpoint leyendo `request.query_params["token"]` en lugar de `Depends(oauth2_scheme)`.
**Warning signs:** 401 en la consola del browser en la conexion /stream.

### Pitfall 4: consecutive_failures no se resetea correctamente en recovery
**What goes wrong:** Un equipo vuelve a responder pero el status sigue DOWN porque el worker no hizo commit a tiempo, o hubo una condicion de carrera.
**Why it happens:** Race condition entre multiples tasks leyendo el mismo device.
**How to avoid:** Asegurarse de que el poll de cada device es un task atomico — un solo worker lee, pinga, actualiza. No distribuir el poll de un mismo device entre varios workers.

### Pitfall 5: Vite proxy no re-escribe el path correctamente para FastAPI
**What goes wrong:** El frontend llama `/api/devices` pero FastAPI tiene el router en `/devices` — el proxy reescribe mal y FastAPI retorna 404.
**Why it happens:** La configuracion de `rewrite` en vite.config.ts tiene que eliminar exactamente el prefijo `/api`.
**How to avoid:** Usar la configuracion de rewrite documentada en Pattern 6. Verificar con `curl http://localhost:5173/api/health`.

### Pitfall 6: CORS rechaza requests con credentials cuando allow_origins es wildcard
**What goes wrong:** El browser rechaza la respuesta del backend con error CORS cuando se envia `credentials: 'include'` y el backend tiene `allow_origins=["*"]`.
**Why it happens:** Especificacion CORS: no se puede tener `*` + `allow_credentials=True` al mismo tiempo.
**How to avoid:** Especificar origen exacto: `allow_origins=["http://localhost:5173"]` en desarrollo; origin de Railway en produccion. [VERIFIED: FastAPI CORS docs]

### Pitfall 7: python-jose instalado como transitive dependency
**What goes wrong:** Algun paquete instala python-jose como dependencia; el codigo mezcla imports de python-jose y PyJWT.
**Why it happens:** Algunas libs antiguas dependen de python-jose.
**How to avoid:** Revisar `pip show python-jose` despues de instalar; si aparece, asegurar que el codigo solo importa `jwt` (PyJWT). PyJWT usa `import jwt`; python-jose usa `from jose import jwt` — diferente namespace.

---

## Code Examples

### JWT Login Endpoint completo

```python
# Source: https://fastapi.tiangolo.com/tutorial/security/oauth2-jwt/ (adaptado para v1)
# backend/app/api/auth.py
from datetime import datetime, timedelta, timezone
from typing import Annotated
import jwt
from pwdlib import PasswordHash
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.core.database import get_db

router = APIRouter(prefix="/auth", tags=["auth"])
password_hash = PasswordHash.recommended()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")
ALGORITHM = "HS256"

def create_access_token(sub: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES  # agregar a Settings
    )
    return jwt.encode({"sub": sub, "exp": expire},
                      settings.SECRET_KEY.get_secret_value(), algorithm=ALGORITHM)

@router.post("/login")
async def login(form: Annotated[OAuth2PasswordRequestForm, Depends()],
                db: AsyncSession = Depends(get_db)):
    user = await get_user_by_username(db, form.username)
    if not user or not password_hash.verify(form.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                           detail="Incorrect username or password",
                           headers={"WWW-Authenticate": "Bearer"})
    return {"access_token": create_access_token(user.username), "token_type": "bearer"}
```

### Celery beat schedule para polling

```python
# Source: Celery docs https://docs.celeryq.dev/en/stable/userguide/periodic-tasks.html
# backend/app/celery_app.py — agregar beat_schedule
from celery.schedules import crontab

app.conf.beat_schedule = {
    "poll-all-devices": {
        "task": "tasks.poll_all_devices",
        "schedule": settings.POLL_INTERVAL_SECONDS,  # 60 segundos
        "options": {"expires": settings.POLL_INTERVAL_SECONDS - 5},  # no acumular si se retrasa
    },
}
app.conf.timezone = "UTC"
```

### Redis pub/sub publisher (en el task de polling)

```python
# Source: https://redis.readthedocs.io/en/stable/examples/asyncio_examples.html
import redis.asyncio as aioredis
import json

async def publish_status_update(device_id: int, status: str) -> None:
    r = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    await r.publish("device_status", json.dumps({"id": device_id, "status": status}))
    await r.aclose()
```

### User model para autenticacion (tabla users a crear via Alembic)

```python
# backend/app/models/user.py — nuevo modelo Phase 2
class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| python-jose + passlib/bcrypt | PyJWT + pwdlib/argon2 | May 2024 (FastAPI PR #11589) | python-jose abandonado; passlib incompatible con Python 3.13+ |
| aioredis (lib separada) | redis.asyncio (builtin en redis-py 4.2+) | 2022 | aioredis fue absorbido; redis==7.4.0 ya incluye redis.asyncio |
| Crear SSE manualmente con StreamingResponse | fastapi.sse.EventSourceResponse | FastAPI 0.135.0 (2024) | Nativo, Pydantic serialization, no requiere lib extra |
| sse-starlette como unica opcion SSE | fastapi.sse nativo | FastAPI 0.135.0 | sse-starlette sigue siendo valido; FastAPI nativo es suficiente |
| icmplib para async ping | subprocess + iputils-ping | Railway limitacion NET_RAW | icmplib requiere NET_RAW que Railway no da |

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | EventSource query param para JWT es aceptable para herramienta interna v1 | Pattern 5 | Si BEEPYRED requiere seguridad mas estricta, necesita httpOnly cookie o WebSocket |
| A2 | Celery polling worker con `--concurrency=1` o `max_instances=1` es suficiente para evitar doble polling | Pitfall 2 | Podrian ejecutarse dos ciclos de polling simultaneamente en Railway si no se configura correctamente |
| A3 | Frontend compilado se servira como StaticFiles desde FastAPI en Phase 2 | Architecture | Si Railway cobra por servicio adicional, esta decision es correcta; si se prefiere Nginx separado, ajustar Dockerfile |

---

## Open Questions

1. **ACCESS_TOKEN_EXPIRE_MINUTES — valor default**
   - What we know: Settings tiene `POLL_INTERVAL_SECONDS`, `DEVICE_TIMEOUT_SECONDS` y otros
   - What's unclear: No hay `ACCESS_TOKEN_EXPIRE_MINUTES` en Settings aun — hay que agregarlo
   - Recommendation: Agregar a `config.py` con default `ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440` (24 horas para que el tecnico no tenga que hacer login cada dia)

2. **ADMIN_USERNAME / ADMIN_PASSWORD para seed user**
   - What we know: No hay endpoint de registro; necesitamos crear el usuario inicial
   - What's unclear: Como se provisionan estas credenciales en Railway
   - Recommendation: Agregar `ADMIN_USERNAME: str = "admin"` y `ADMIN_PASSWORD: SecretStr` a Settings; script de seed que corre como Railway pre-deploy command (junto con alembic upgrade head)

3. **Frontend deploy — StaticFiles vs servicio Nginx separado**
   - What we know: Stack doc menciona bundling con FastAPI StaticFiles para minimizar servicios Railway
   - What's unclear: El Dockerfile actual no tiene stage para el frontend Vite
   - Recommendation: Agregar stage `frontend-build` al Dockerfile multi-stage que compila Vite, y copiar el `dist/` al stage `web`. FastAPI sirve con `StaticFiles(directory="dist")`.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Node.js | Frontend Vite build | ✓ | v24.14.0 | — |
| npm | Frontend packages | ✓ | 11.9.0 | — |
| Python 3.12 | Backend | ✓ (Railway Dockerfile) | 3.12-slim | — |
| PostgreSQL | Device/User data | ✓ (Railway addon) | 16 | — |
| Redis | Broker + pub/sub | ✓ (Railway addon) | 7.x | — |
| iputils-ping | ICMP polling | ✗ (no en imagen slim) | — | Agregar en Dockerfile: `apt-get install -y iputils-ping` |
| PyJWT | JWT auth | ✗ (no en requirements.txt) | — | Agregar a requirements.txt: `pyjwt` |
| pwdlib[argon2] | Password hashing | ✗ (no en requirements.txt) | — | Agregar a requirements.txt: `pwdlib[argon2]` |

**Missing dependencies con no-fallback (bloquean ejecucion):**
- `iputils-ping`: sin este el ICMP ping falla en Railway. Solucion: Dockerfile stage base.
- `pyjwt` + `pwdlib[argon2]`: sin estos el auth no compila. Solucion: requirements.txt.

**Missing dependencies con fallback:**
- Ninguno — los tres bloqueos tienen solucion clara.

---

## Validation Architecture

**nyquist_validation: true en config.json — esta seccion es obligatoria.**

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 8.3.5 + pytest-asyncio 0.25.3 |
| Config file | `backend/pytest.ini` (testpaths = tests/unit) |
| Quick run command | `cd backend && python -m pytest tests/unit/ -x -q` |
| Full suite command | `cd backend && python -m pytest tests/ -v --cov=app` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| AUTH-01 | Login retorna JWT valido con credenciales correctas | unit | `pytest tests/unit/test_auth.py::test_login_success -x` | ❌ Wave 0 |
| AUTH-01 | Login retorna 401 con credenciales incorrectas | unit | `pytest tests/unit/test_auth.py::test_login_failure -x` | ❌ Wave 0 |
| AUTH-02 | JWT expira segun ACCESS_TOKEN_EXPIRE_MINUTES | unit | `pytest tests/unit/test_auth.py::test_token_expiry -x` | ❌ Wave 0 |
| AUTH-03 | Endpoint protegido retorna 401 sin token | unit | `pytest tests/unit/test_auth.py::test_protected_requires_auth -x` | ❌ Wave 0 |
| INV-01 | POST /devices crea equipo con campos requeridos | unit | `pytest tests/unit/test_devices.py::test_create_device -x` | ❌ Wave 0 |
| INV-03 | PUT /devices/{id} actualiza; DELETE /devices/{id} elimina | unit | `pytest tests/unit/test_devices.py::test_update_delete_device -x` | ❌ Wave 0 |
| POLL-01 | Celery beat schedule tiene poll_all_devices a 60s | unit | `pytest tests/unit/test_polling.py::test_beat_schedule -x` | ❌ Wave 0 |
| POLL-02 | ping_host respeta Semaphore(50) — maximo 50 concurrentes | unit | `pytest tests/unit/test_polling.py::test_semaphore_limit -x` | ❌ Wave 0 |
| POLL-03 | consecutive_failures se incrementa en fallo; reset en exito; DOWN tras 3 | unit | `pytest tests/unit/test_polling.py::test_consecutive_failures_debounce -x` | ❌ Wave 0 |
| POLL-05 | ping_host retorna False antes de timeout + 1s si host no responde | unit | `pytest tests/unit/test_polling.py::test_ping_timeout -x` | ❌ Wave 0 |
| POLL-04 | SSE endpoint retorna 200 text/event-stream | smoke | `curl -N http://localhost:8000/devices/stream?token=... --max-time 3` | ❌ manual |

**Tests que son manual-only:**
- POLL-04 SSE en produccion Railway: requiere browser real con EventSource. El test de smoke con curl es suficiente para CI.
- INV-04 estado UP/DOWN en tiempo real end-to-end: requiere Celery worker corriendo. Validar en integration test separado.

### Sampling Rate

- **Per task commit:** `cd backend && python -m pytest tests/unit/ -x -q`
- **Per wave merge:** `cd backend && python -m pytest tests/unit/ -v --cov=app --cov-report=term-missing`
- **Phase gate:** Full suite green antes de `/gsd-verify-work`

### Wave 0 Gaps

- [ ] `backend/tests/unit/test_auth.py` — cubre AUTH-01, AUTH-02, AUTH-03
- [ ] `backend/tests/unit/test_devices.py` — cubre INV-01, INV-03
- [ ] `backend/tests/unit/test_polling.py` — cubre POLL-01, POLL-02, POLL-03, POLL-05
- [ ] `backend/app/models/user.py` — modelo User (tabla users) para auth
- [ ] Alembic migration `002_add_users_table.py` — tabla users + access_token_expire_minutes en settings
- [ ] `frontend/` directory — inicializar con Vite + shadcn

---

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes | PyJWT + pwdlib/Argon2; OAuth2PasswordBearer; no registro publico |
| V3 Session Management | yes | JWT con expiracion configurable; no refresh tokens en v1 |
| V4 Access Control | yes | `get_current_active_user` Depends en todos los endpoints CRUD y SSE |
| V5 Input Validation | yes | Pydantic v2 schemas para DeviceCreate, DeviceUpdate |
| V6 Cryptography | yes | Argon2 para passwords; HS256 para JWT; Fernet para device credentials (Phase 1) |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| JWT secret key debil | Spoofing | `SECRET_KEY` es SecretStr; generar con `secrets.token_hex(32)` — ya documentado en .env.example |
| Token en localStorage robado via XSS | Information Disclosure | Para v1 herramienta interna es aceptable; mitigar con Content-Security-Policy header |
| Timing attack en login | Spoofing | Verificar password incluso si user no existe (DUMMY_HASH) — patron documentado en FastAPI docs |
| SSE stream sin auth | Elevation of Privilege | Token JWT como query param validado en el endpoint SSE antes de iniciar stream |
| IP spoofing en inventario | Tampering | Validar formato IP con Pydantic `IPvAnyAddress` — previene inyeccion de IPs invalidas |
| ICMP flood si inventario crece | DoS (propio) | asyncio.Semaphore(50) limita concurrencia; si se superan 500 equipos en un ciclo de 60s, revisar batch size |

---

## Sources

### Primary (HIGH confidence)
- [FastAPI JWT docs — github.com/fastapi] — PyJWT + pwdlib recomendacion oficial, codigo verificado 2024-2025
- [FastAPI SSE docs — fastapi.tiangolo.com/tutorial/server-sent-events] — EventSourceResponse en fastapi.sse nativo desde 0.135.0
- [Railway station — station.railway.com — NET_RAW] — Railway confirma que `NET_RAW` no esta disponible; iputils-ping moderno usa datagram sockets
- [redis-py asyncio examples — redis.readthedocs.io] — redis.asyncio pub/sub patron verificado
- [shadcn/ui Vite install — ui.shadcn.com/docs/installation/vite] — instalacion oficial verificada

### Secondary (MEDIUM confidence)
- [FastAPI discussions #11345, #9587, PR #11589] — abandono de python-jose y python-jose→PyJWT migration documentados en GitHub
- [FastAPI discussions #11773] — abandono de passlib documentado
- [Python asyncio subprocess docs] — asyncio.create_subprocess_exec + asyncio.wait_for patron

### Tertiary (LOW confidence — verificar en ejecucion)
- [Celery asyncio integration] — asyncio.run() dentro de task sincronico Celery; comportamiento con multiple workers sin coordinacion es [ASSUMED]
- [EventSource query param para JWT] — patron de seguridad aceptable para herramienta interna; no verificado con politica especifica de BEEPYRED

---

## Metadata

**Confidence breakdown:**
- JWT Auth (PyJWT + pwdlib): HIGH — cambio documentado en FastAPI docs oficiales
- ICMP via subprocess ping: HIGH — Railway confirma limitacion NET_RAW; iputils-ping es la solucion documentada por Railway
- SSE fastapi.sse nativo: HIGH — disponible en FastAPI 0.135.0, ya instalado como 0.136.1
- Frontend stack (Vite + shadcn): HIGH — documentacion oficial shadcn verificada
- Celery + asyncio bridge: MEDIUM — asyncio.run() es el patron correcto pero comportamiento multi-worker necesita validacion
- consecutive_failures en DB: HIGH — modelo ya creado en Phase 1 con el campo exacto

**Research date:** 2026-04-26
**Valid until:** 2026-05-26 (30 dias — stack estable)
