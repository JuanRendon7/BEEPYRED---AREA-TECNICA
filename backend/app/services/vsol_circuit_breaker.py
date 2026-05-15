"""
Circuit breaker por OLT VSOL usando Redis TTL.

VSOL-04: Suspende polling SSH 5 minutos tras 3 fallos consecutivos.
Separado del circuit breaker Mikrotik (prefijo 'cb:').

Claves Redis:
  vsol:fails:{device_id}  — contador de fallos (expira en CIRCUIT_OPEN_TTL)
  vsol:open:{device_id}   — indica circuit abierto (TTL = tiempo de suspension)
"""
import redis.asyncio as aioredis

_PREFIX = "vsol"
CIRCUIT_OPEN_TTL: int = 5 * 60   # 5 minutos (VSOL-04)
CIRCUIT_FAIL_THRESHOLD: int = 3  # 3 fallos SSH consecutivos


async def is_vsol_circuit_open(redis_client: aioredis.Redis, device_id: int) -> bool:
    """True si el circuit breaker VSOL esta abierto para esta OLT."""
    return await redis_client.exists(f"{_PREFIX}:open:{device_id}") > 0


async def record_vsol_failure(redis_client: aioredis.Redis, device_id: int) -> bool:
    """
    Incrementa contador de fallos SSH VSOL.
    Si alcanza CIRCUIT_FAIL_THRESHOLD, abre el circuit (setex con TTL).
    Retorna True si el circuit acaba de abrirse.
    """
    fail_key = f"{_PREFIX}:fails:{device_id}"
    count = await redis_client.incr(fail_key)
    await redis_client.expire(fail_key, CIRCUIT_OPEN_TTL)

    if count >= CIRCUIT_FAIL_THRESHOLD:
        await redis_client.setex(f"{_PREFIX}:open:{device_id}", CIRCUIT_OPEN_TTL, "1")
        await redis_client.delete(fail_key)
        return True
    return False


async def record_vsol_success(redis_client: aioredis.Redis, device_id: int) -> None:
    """Resetea el circuit breaker VSOL al conectar exitosamente."""
    await redis_client.delete(f"{_PREFIX}:fails:{device_id}")
    await redis_client.delete(f"{_PREFIX}:open:{device_id}")
