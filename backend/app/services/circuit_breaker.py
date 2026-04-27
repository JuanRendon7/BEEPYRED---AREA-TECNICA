"""
Circuit breaker por dispositivo usando Redis TTL.

MK-04: Suspende polling RouterOS API 5 minutos tras 3 fallos consecutivos.
Separado del circuit breaker ICMP (consecutive_failures en DB).

Claves Redis:
  cb:fails:{device_id}  — contador de fallos (expira en CIRCUIT_OPEN_TTL)
  cb:open:{device_id}   — indica circuit abierto (TTL = tiempo de suspension)
"""
import redis.asyncio as aioredis

CIRCUIT_OPEN_TTL: int = 5 * 60   # 5 minutos (MK-04)
CIRCUIT_FAIL_THRESHOLD: int = 3  # 3 fallos RouterOS API consecutivos


async def is_circuit_open(redis_client: aioredis.Redis, device_id: int) -> bool:
    """True si el circuit breaker esta abierto para este dispositivo."""
    return await redis_client.exists(f"cb:open:{device_id}") > 0


async def record_api_failure(redis_client: aioredis.Redis, device_id: int) -> bool:
    """
    Incrementa contador de fallos RouterOS API.
    Si alcanza CIRCUIT_FAIL_THRESHOLD, abre el circuit (setex con TTL).
    Retorna True si el circuit acaba de abrirse.
    """
    fail_key = f"cb:fails:{device_id}"
    count = await redis_client.incr(fail_key)
    await redis_client.expire(fail_key, CIRCUIT_OPEN_TTL)

    if count >= CIRCUIT_FAIL_THRESHOLD:
        await redis_client.setex(f"cb:open:{device_id}", CIRCUIT_OPEN_TTL, "1")
        await redis_client.delete(fail_key)
        return True
    return False


async def record_api_success(redis_client: aioredis.Redis, device_id: int) -> None:
    """Resetea el circuit breaker al conectar exitosamente."""
    await redis_client.delete(f"cb:fails:{device_id}")
    await redis_client.delete(f"cb:open:{device_id}")
