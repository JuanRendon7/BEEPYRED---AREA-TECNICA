from fastapi import FastAPI

app = FastAPI(title="BEEPYRED NOC", version="1.0.0")


@app.get("/health")
async def health_check() -> dict:
    """Health check endpoint — requerido por railway.toml healthcheckPath."""
    return {"status": "ok", "service": "web"}
