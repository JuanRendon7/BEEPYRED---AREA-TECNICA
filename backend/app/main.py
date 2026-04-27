from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api import auth as auth_router
from app.api import devices as devices_router
from app.api import events as events_router

app = FastAPI(
    title="BEEPYRED NOC",
    version="2.0.0",
    description="Network Operations Center — BEEPYRED ISP GROUP SAS",
)

# CORS: especificar origenes exactos (NO usar wildcard con credentials=True)
# En produccion Railway, el frontend se sirve desde el mismo origen — esto es para dev local.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",   # Vite dev server (Plan 04)
        "http://localhost:3000",   # alternativa dev
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router.router)
app.include_router(devices_router.router)
app.include_router(events_router.router)


@app.get("/health")
async def health_check() -> dict:
    """Health check endpoint — requerido por railway.toml healthcheckPath."""
    return {"status": "ok", "service": "web", "version": "2.0.0"}
