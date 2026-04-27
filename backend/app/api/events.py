"""
Endpoint SSE — Server-Sent Events para actualizaciones en tiempo real.

POLL-05: El browser se suscribe a GET /events?token=... y recibe eventos
cuando el worker cambia el estado de un dispositivo.

CRITICO — EventSource y JWT:
    El browser EventSource NO soporta el header Authorization.
    Solucion v1 (herramienta interna): token como query param ?token=...
    El endpoint valida el JWT manualmente con jwt.decode().

CRITICO — StreamingResponse con text/event-stream:
    Se usa StreamingResponse directamente con media_type="text/event-stream".
    Es el patron mas simple y compatible con FastAPI.

Flujo:
    1. Browser GET /events?token=<jwt>
    2. Endpoint valida JWT → retorna 401 si invalido
    3. Suscripcion a Redis canal 'device_status' via redis.asyncio pub/sub
    4. Por cada mensaje Redis: yield "data: {json}\\n\\n"
    5. Browser onmessage: actualiza estado del device en UI

Mitigacion T-2-32: _validate_sse_token() valida JWT antes de iniciar stream.
Mitigacion T-2-33: request.is_disconnected() cierra suscripcion Redis al desconectar.
"""
import json

import jwt
import redis.asyncio as aioredis
from fastapi import APIRouter, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse

from app.core.config import settings
from app.core.auth import ALGORITHM

router = APIRouter(prefix="/events", tags=["events"])


def _validate_sse_token(token: str) -> str:
    """
    Valida JWT recibido como query param en SSE.
    Retorna username si valido. Lanza HTTPException 401 si invalido.

    T-2-32: Validacion obligatoria antes de iniciar el stream SSE.
    """
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY.get_secret_value(),
            algorithms=[ALGORITHM],
        )
        username: str | None = payload.get("sub")
        if username is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token SSE invalido — sub ausente",
            )
        return username
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token SSE expirado",
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token SSE invalido",
        )


@router.get("")
async def device_status_stream(
    request: Request,
    token: str = Query(..., description="JWT Bearer token del tecnico"),
) -> StreamingResponse:
    """
    POLL-05: Stream SSE de cambios de estado de dispositivos.

    Uso desde browser:
        const es = new EventSource(`/events?token=${localStorage.getItem('token')}`);
        es.onmessage = (e) => { const update = JSON.parse(e.data); ... };

    Cada evento tiene el formato:
        data: {"id": 5, "status": "down"}

    La conexion se mantiene abierta hasta que el cliente desconecta.
    """
    # T-2-32: Validar JWT antes de iniciar el stream
    _validate_sse_token(token)

    async def event_generator():
        r = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
        pubsub = r.pubsub()
        await pubsub.subscribe("device_status")
        try:
            # Enviar comment de keep-alive inicial para confirmar conexion
            yield ":\n\n"
            async for message in pubsub.listen():
                # T-2-33: Verificar que el cliente sigue conectado
                if await request.is_disconnected():
                    break
                if message["type"] == "message":
                    data = message["data"]
                    # Formato SSE: "data: <json>\n\n"
                    yield f"data: {data}\n\n"
        finally:
            await pubsub.unsubscribe("device_status")
            await r.aclose()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # Desactiva buffering en Nginx
            "Connection": "keep-alive",
        },
    )
