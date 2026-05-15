# Phase 4: VSOL OLT Collector — Research

**Investigado:** 2026-05-14
**Dominio:** asyncssh SSH a VSOL GPON OLT, parseo CLI V2.3.1R, upsert de ONUs, circuit breaker por OLT
**Confianza global:** HIGH para asyncssh y patrones de upsert; MEDIUM para formato exacto de salida CLI (requiere validación hands-on)

---

## Contexto de hardware confirmado (OLT backup analizado 2026-05-14)

| Campo | Valor | Fuente |
|-------|-------|--------|
| Hostname | `BeepyRed_OLT_GPON_SanLuis` | backup OLT |
| IP de gestión | `192.168.8.200` | backup OLT |
| Firmware | V2.3.1R (build 25/01/2024) | backup OLT |
| SSH version | v2, RSA 2048-bit SHA256 | backup OLT / screenshot SSH config |
| Sesiones SSH máx | 3 | backup OLT |
| Timeout SSH | 60s | backup OLT |
| Redes permitidas SSH | `192.168.80.0/24`, `192.168.8.0/24` | backup OLT |
| Puertos GPON | 8 (`gpon 0/1` → `gpon 0/8`) | backup OLT |
| ONUs registradas | ~597 en total | backup OLT |
| OLTs EPON | 0 (ninguna — diferido) | usuario confirmó |
| Telnet | Denegado globalmente | backup OLT |
| SNMP | Denegado globalmente | backup OLT |
| Auto-learn ONUs | Activo en todos los puertos — perfil `Perfil1` | backup OLT |
| VLAN clientes | 1001 | backup OLT |

**Bloqueador anterior resuelto:** El STATE.md tenía riesgo de "comandos CLI VSOL varían por modelo y firmware — requiere sesión hands-on". El backup confirma modelo único y firmware V2.3.1R — los parsers se pueden escribir con confianza MEDIUM.

---

<phase_requirements>
## Requisitos de Phase 4

| ID | Descripción | Soporte en investigación |
|----|-------------|--------------------------|
| VSOL-01 | SSH a OLTs VSOL GPON (8 puertos), lista ONUs con ONLINE/OFFLINE/RANGING y señal Rx/Tx dBm | asyncssh + `show pon onu state` + `show pon optical-info` |
| VSOL-02 | SSH a OLTs VSOL EPON (4 puertos) | **DIFERIDO** — usuario confirmó que no hay OLT EPON actualmente |
| VSOL-03 | Conexiones SSH con timeout duro 30s, cierre correcto | asyncssh `connect_timeout`, `async with` garantiza cierre |
| VSOL-04 | Circuit breaker por OLT — suspende tras 3 fallos, sin afectar resto | Reuso de `app.services.circuit_breaker` con prefijo `vsol:` |
| VSOL-05 | Cada ONU en inventario con OLT padre y puerto PON | Upsert en tablas `devices` + `onus` |
</phase_requirements>

---

## Hallazgos por dominio de investigación

### 1. asyncssh — Patrón correcto para CLI VSOL

**Versión actual en stack:** No instalada — `asyncssh>=2.14.0` debe agregarse a `requirements.txt`.

asyncssh es la librería recomendada en el tech stack para SSH a OLTs. Es async-native y compatible con el patrón `asyncio.run()` ya establecido en los tasks Celery.

#### Patrón recomendado — una sesión SSH por ciclo de polling

```python
# Fuente: asyncssh docs oficiales [VERIFIED: asyncssh.readthedocs.io]
import asyncssh

async def _collect_vsol_olt(host: str, username: str, password: str) -> list[dict]:
    """
    Abre UNA sola conexión SSH al OLT y ejecuta todos los comandos secuencialmente.
    Respeta el límite de 3 sesiones SSH simultáneas del OLT.
    """
    async with asyncssh.connect(
        host,
        username=username,
        password=password,
        known_hosts=None,           # aceptar cualquier host key — red privada ISP
        connect_timeout=30,         # VSOL-03: timeout duro 30s
        login_timeout=30,
    ) as conn:
        onus = []
        for port in range(1, 9):   # puertos gpon 0/1 a gpon 0/8
            result = await conn.run(
                f"show pon onu state gpon 0/{port}",
                timeout=30,
            )
            port_onus = _parse_onu_state(result.stdout, port)
            onus.extend(port_onus)
        return onus
```

**Por qué una sesión SSH y no 8 paralelas:**
- El OLT tiene límite de 3 sesiones SSH simultáneas (confirmado en backup)
- Una sola sesión ejecuta 8 comandos secuencialmente en ~2-3 segundos total
- Evita saturar la OLT con conexiones simultáneas

#### asyncssh `async with` garantiza cierre (VSOL-03)

El context manager `async with asyncssh.connect()` cierra la conexión SSH automáticamente al salir del bloque, incluso si hay excepción. Equivale a `conn.close()` en `finally`. No hay sesiones zombie.

```python
# async with asyncssh.connect() es equivalente a:
conn = await asyncssh.connect(...)
try:
    # ... comandos
finally:
    conn.close()  # cierre garantizado
```

#### connect_timeout en asyncssh

- `connect_timeout=30`: tiempo máximo para establecer la conexión TCP + SSH handshake
- `login_timeout=30`: tiempo máximo para autenticación
- `timeout=30` en `conn.run()`: tiempo máximo por comando individual

Los tres son necesarios para VSOL-03 (timeout duro de 30s). En la práctica, el timeout crítico es `connect_timeout` para conexiones fallidas.

#### known_hosts=None — red privada

Para equipos en red privada ISP, `known_hosts=None` desactiva la verificación de host key. Equivalente a `ssh -o StrictHostKeyChecking=no`. Aceptable para red interna donde no hay riesgo de MITM.

**Alternativa más segura:** capturar la host key del OLT en primera conexión y guardarla. Para v1 con red privada, `known_hosts=None` es suficiente.

---

### 2. Formato CLI VSOL V2.3.1R — Comandos y salida esperada

**IMPORTANTE — Confianza MEDIUM:** El formato de salida documentado abajo está basado en conocimiento de VSOL V2.x y patrones de CLI de OLTs GPON. Las columnas y nombres de campo deben validarse contra el hardware real en la primera ejecución. Los parsers usan regex y `.get()` defensivo para tolerar variaciones.

#### Comando 1: `show pon onu state gpon 0/X`

Retorna estado de todas las ONUs registradas en el puerto X.

**Salida esperada (ASSUMED — VSOL V2.3.1R):**
```
 ONU-index          SN               Auth-type  ONU-state  ONU-status  Distance(m)
 ---------------------------------------------------------------------------------
 gpon-onu_0/1:1     4857454c12345601  SN         ONLINE     OK          1234
 gpon-onu_0/1:2     4857454c12345602  SN         OFFLINE    -           -
 gpon-onu_0/1:3     4857454c12345603  SN         RANGING    -           -
```

**Campos relevantes:**
- `ONU-index`: formato `gpon-onu_0/PORT:ONU_NUM` — identifica ONU dentro del puerto
- `SN`: número de serie en hexadecimal (16 chars) — identificador único de ONU
- `ONU-state`: `ONLINE`, `OFFLINE`, `RANGING` — estado GPON del ONU

**Regex para parsear línea de ONU:**
```python
import re
_ONU_STATE_RE = re.compile(
    r"gpon-onu_0/(\d+):(\d+)\s+"   # grupo 1=puerto, grupo 2=onu_num
    r"(\S+)\s+"                      # grupo 3=serial_number
    r"\S+\s+"                        # auth-type (ignorar)
    r"(ONLINE|OFFLINE|RANGING)"      # grupo 4=state
)
```

#### Comando 2: `show pon optical-info gpon 0/X onu N`

Retorna señal óptica de una ONU específica (solo funciona para ONUs ONLINE).

**Salida esperada (ASSUMED — VSOL V2.3.1R):**
```
ONU-index           : gpon-onu_0/1:1
Rx power(dBm)       : -19.47
Tx power(dBm)       :  2.00
OLT Rx power(dBm)   : -21.34
Temperature(C)      :  50
Voltage(V)          :  3.26
Bias-current(mA)    : 15.21
```

**Campos relevantes:**
- `Rx power(dBm)`: señal óptica recibida por ONU — `signal_rx_dbm` en DB
- `Tx power(dBm)`: señal óptica transmitida por ONU — `signal_tx_dbm` en DB

**Regex para parsear:**
```python
_RX_RE = re.compile(r"Rx power\(dBm\)\s*:\s*(-?[\d.]+)")
_TX_RE = re.compile(r"Tx power\(dBm\)\s*:\s*(-?[\d.]+)")
```

#### Alternativa: `show pon optical-info gpon 0/X` (sin `onu N`)

Si VSOL V2.3.1R soporta este comando, retorna optical-info de TODAS las ONUs ONLINE en el puerto en una tabla. Esto reduciría los comandos SSH de `N_online_onus_por_puerto` a 1 por puerto.

**Estado:** No confirmado para V2.3.1R. [ASSUMED que NO existe — plan conservador]
**Validación requerida:** En primera ejecución, intentar este comando y loggear resultado.

#### Estrategia de polling adoptada

Con ~597 ONUs y polling cada 60s:
- 8 comandos `show pon onu state gpon 0/X` → ~2s total de SSH (fast)
- Para señal óptica: por ONU ONLINE con `show pon optical-info gpon 0/X onu N`
  - Si hay ~400 online: 400 comandos × ~0.3s = 120s → **demasiado lento para ciclo de 60s**

**Solución:** Separar en dos ciclos Celery beat con intervalos distintos:
- `poll-vsol-olt-state`: cada 60s — solo estado (8 comandos)
- `poll-vsol-olt-optical`: cada 5min (300s) — estado + señal óptica de ONLINE ONUs

```python
# Celery beat — dos tasks con intervalos distintos
"poll-vsol-state": {
    "task": "tasks.poll_vsol_olt_state",
    "schedule": settings.POLL_INTERVAL_SECONDS,  # 60s
},
"poll-vsol-optical": {
    "task": "tasks.poll_vsol_olt_optical",
    "schedule": settings.VSOL_OPTICAL_POLL_INTERVAL,  # 300s
},
```

Nueva setting: `VSOL_OPTICAL_POLL_INTERVAL: int = 300`

---

### 3. Circuit breaker por OLT — Reuso de circuit_breaker.py

El módulo `app.services.circuit_breaker` de Phase 3 ya implementa el patrón correcto con Redis TTL. Para Phase 4, se reutiliza con un prefijo de clave diferente para evitar colisión con el circuit breaker de Mikrotik.

| Prefijo | Uso |
|---------|-----|
| `cb:open:{id}` | Circuit breaker RouterOS API (Phase 3) |
| `cb:fails:{id}` | Contador fallos RouterOS API (Phase 3) |
| `vsol:open:{id}` | Circuit breaker SSH VSOL OLT (Phase 4) |
| `vsol:fails:{id}` | Contador fallos SSH VSOL OLT (Phase 4) |

Las funciones `is_circuit_open()`, `record_api_failure()`, `record_api_success()` ya aceptan el cliente Redis y el device_id — solo se necesita un wrapper que use las claves con prefijo `vsol:`.

**Opción A — Wrapper simple (recomendada):**
```python
# app/services/vsol_circuit_breaker.py
from app.services.circuit_breaker import (
    CIRCUIT_FAIL_THRESHOLD,
    CIRCUIT_OPEN_TTL,
)

VSOL_KEY_PREFIX = "vsol"

async def is_vsol_circuit_open(redis_client, device_id: int) -> bool:
    return await redis_client.exists(f"{VSOL_KEY_PREFIX}:open:{device_id}") > 0

async def record_vsol_failure(redis_client, device_id: int) -> bool:
    fail_key = f"{VSOL_KEY_PREFIX}:fails:{device_id}"
    count = await redis_client.incr(fail_key)
    await redis_client.expire(fail_key, CIRCUIT_OPEN_TTL)
    if count >= CIRCUIT_FAIL_THRESHOLD:
        await redis_client.setex(f"{VSOL_KEY_PREFIX}:open:{device_id}", CIRCUIT_OPEN_TTL, "1")
        await redis_client.delete(fail_key)
        return True
    return False

async def record_vsol_success(redis_client, device_id: int) -> None:
    await redis_client.delete(f"{VSOL_KEY_PREFIX}:fails:{device_id}")
    await redis_client.delete(f"{VSOL_KEY_PREFIX}:open:{device_id}")
```

**Opción B — Refactorizar circuit_breaker.py con prefijo configurable (alternativa):**
Más DRY pero más cambio en código existente que ya tiene tests. Preferir Opción A para Phase 4.

---

### 4. ONU upsert — Estrategia de inventario (VSOL-05)

Cada ONU debe existir en dos tablas:
1. `devices` — para aparecer en el inventario general (con type=ONU, parent_device_id=OLT.id)
2. `onus` — para almacenar señal, número de serie y relación OLT/puerto

**El campo `ip_address` en `devices` es NOT NULL.** Las ONUs GPON no tienen IPs routeables visibles desde el NOC. Convención adoptada: usar el serial number como pseudo-IP en formato `onu:{serial}` — pero `String(45)` limita a 45 chars, y `onu:4857454c12345678` tiene 20 chars, lo cual cabe.

**Alternativa más limpia:** guardar `"0.0.0.0"` como `ip_address` de la ONU. Pero esto haría que el ICMP poller las incluya y las marque DOWN.

**Solución adoptada:** usar `"0.0.0.0"` pero excluir `DeviceType.ONU` del ciclo ICMP polling. Requiere modificar `_poll_all_devices_async` en `polling.py` para agregar el filtro.

**Estrategia upsert:**
```python
# Buscar ONU existente por serial_number en tabla onus
# Si no existe: crear Device + ONU record
# Si existe: actualizar onu_status, signal_rx_dbm, signal_tx_dbm, last_updated_at
# También actualizar devices.status basado en onu_status

from sqlalchemy.dialects.postgresql import insert as pg_insert

async def upsert_onu(
    db: AsyncSession,
    olt_id: int,
    pon_port: str,
    serial_number: str,
    onu_status: str,
    signal_rx_dbm: float | None,
    signal_tx_dbm: float | None,
    onu_name: str,
) -> None:
    """
    Busca ONU por serial_number, crea si no existe, actualiza señal/estado.
    """
    # 1. Buscar ONU en tabla onus por serial_number
    result = await db.execute(
        select(ONU).where(ONU.serial_number == serial_number)
    )
    onu_record = result.scalar_one_or_none()

    if onu_record is None:
        # Crear Device para la ONU
        new_device = Device(
            name=onu_name,          # ej: "ONU gpon-0/1:1 (4857454c...)"
            ip_address="0.0.0.0",  # ONU no tiene IP routable
            device_type=DeviceType.ONU,
            parent_device_id=olt_id,
            pon_port=pon_port,
            status=DeviceStatus.UP if onu_status == "ONLINE" else DeviceStatus.UNKNOWN,
            is_active=True,
        )
        db.add(new_device)
        await db.flush()  # obtener ID asignado

        # Crear ONU record
        onu_record = ONU(
            device_id=new_device.id,
            olt_id=olt_id,
            serial_number=serial_number,
            pon_port=pon_port,
        )
        db.add(onu_record)

    # 2. Actualizar estado y señal
    onu_record.onu_status = onu_status
    onu_record.signal_rx_dbm = signal_rx_dbm
    onu_record.signal_tx_dbm = signal_tx_dbm
    onu_record.last_updated_at = datetime.now(timezone.utc)

    # 3. Actualizar Device.status basado en estado GPON
    result = await db.execute(
        select(Device).where(Device.id == onu_record.device_id)
    )
    device = result.scalar_one_or_none()
    if device:
        device.status = DeviceStatus.UP if onu_status == "ONLINE" else DeviceStatus.DOWN
        device.last_seen_at = datetime.now(timezone.utc) if onu_status == "ONLINE" else device.last_seen_at
```

**Optimización para 597 ONUs — batch commit:**
En lugar de un commit por ONU (597 commits), acumular todos los cambios y hacer un solo commit al final del ciclo de polling del OLT.

---

### 5. Señal óptica — Alerta Telegram (ALERT-03)

`ALERT-03` está marcado como `[x]` en REQUIREMENTS.md, pero la infraestructura de alertas (Telegram, `get_threshold`) fue construida en Phase 3. Lo que falta es el **trigger** de la alerta de señal baja.

El trigger va en el task VSOL collector: después de actualizar `signal_rx_dbm`, si el valor está por debajo del umbral, disparar alerta Telegram usando el pipeline existente.

```python
from app.services.telegram import send_telegram_alert
from app.services.thresholds import get_threshold

async def _check_signal_alert(
    db: AsyncSession,
    onu_device_id: int,
    onu_name: str,
    pon_port: str,
    signal_rx_dbm: float,
    olt_site: str | None,
) -> None:
    threshold = await get_threshold(db, "signal_low", device_id=onu_device_id)
    if threshold is not None and signal_rx_dbm < threshold:
        text = (
            f"📡 <b>SEÑAL ONU BAJA</b>\n"
            f"<b>ONU:</b> {onu_name}\n"
            f"<b>Puerto:</b> {pon_port}\n"
            f"<b>Rx:</b> <code>{signal_rx_dbm:.2f} dBm</code> "
            f"(umbral: {threshold:.1f} dBm)\n"
            f"<b>Sitio:</b> {olt_site or 'Sin sitio'}"
        )
        await send_telegram_alert(text)
```

**Debounce para señal ONU:** La señal óptica puede fluctuar. Para evitar spam de alertas, implementar debounce similar al de Phase 3:
- Clave Redis `vsol:signal_alert:{onu_device_id}` con TTL = 1 hora
- Si la clave existe: no reenviar alerta de señal baja

---

### 6. Modificación a polling.py — Excluir ONUs de ICMP

Con ONUs registradas en `devices` con `ip_address="0.0.0.0"`, el ICMP poller las incluiría y las marcaría DOWN constantemente.

**Cambio requerido en `_poll_all_devices_async`:**
```python
# ANTES (Phase 2):
result = await db.execute(
    select(Device).where(Device.is_active == True)
)

# DESPUÉS (Phase 4):
result = await db.execute(
    select(Device)
    .where(Device.is_active == True)
    .where(Device.device_type != DeviceType.ONU)  # ONUs no tienen IP routable
)
```

Este cambio es backwards-compatible — ninguna ONU existía antes de Phase 4.

---

### 7. GET /api/v1/onus — Endpoint de inventario ONUs

Endpoint para listar ONUs con filtros, usando el patrón JOIN ya establecido en `/incidents`.

```python
@router.get("/onus", response_model=list[ONUResponse])
async def list_onus(
    olt_id: int | None = None,
    pon_port: str | None = None,
    status: str | None = None,  # "ONLINE", "OFFLINE", "RANGING"
    limit: int = 100,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_current_user),
):
    query = (
        select(ONU, Device.name, Device.site)
        .join(Device, ONU.device_id == Device.id)
        .order_by(ONU.olt_id, ONU.pon_port)
        .limit(limit)
        .offset(offset)
    )
    if olt_id:
        query = query.where(ONU.olt_id == olt_id)
    if pon_port:
        query = query.where(ONU.pon_port == pon_port)
    if status:
        query = query.where(ONU.onu_status == status)
    result = await db.execute(query)
    return [dict(row._mapping) for row in result.all()]
```

---

## Stack para Phase 4

### Nueva dependencia

| Librería | Versión | Propósito |
|----------|---------|-----------|
| `asyncssh` | `>=2.14.0` | SSH async a OLT VSOL (VSOL-01, VSOL-03) |

### Ya presentes (no agregar)

| Librería | Uso en Phase 4 |
|----------|----------------|
| `redis==7.4.0` | Circuit breaker VSOL (prefijo vsol:) |
| `sqlalchemy[asyncio]==2.0.49` | ONU upsert en tables devices + onus |
| `celery[redis]==5.6.3` | Tasks poll_vsol_olt_state, poll_vsol_olt_optical |
| `python-telegram-bot==21.*` | Alertas señal baja ONU |
| `cryptography==47.0.0` | Descifrado credenciales SSH Fernet |

---

## Estructura de archivos Phase 4

```
backend/app/
├── tasks/
│   └── vsol.py               # nuevo — poll_vsol_olt_state, poll_vsol_olt_optical
├── services/
│   └── vsol_circuit_breaker.py  # nuevo — circuit breaker con prefijo vsol:
├── collectors/
│   └── vsol_parser.py        # nuevo — parsers CLI: parse_onu_state, parse_optical_info
├── api/v1/
│   └── onus.py               # nuevo — GET /api/v1/onus con filtros JWT
└── schemas/
    └── onu.py                # nuevo — ONUResponse Pydantic schema
```

Cambios en existentes:
- `backend/app/tasks/polling.py` — agregar filtro `.where(Device.device_type != DeviceType.ONU)`
- `backend/app/celery_app.py` — agregar include + beat_schedule para VSOL tasks
- `backend/app/core/config.py` — agregar `VSOL_SSH_PORT`, `VSOL_SSH_TIMEOUT`, `VSOL_OPTICAL_POLL_INTERVAL`
- `backend/requirements.txt` — agregar `asyncssh>=2.14.0`
- Frontend: nueva página `ONUs.tsx` con tabla

---

## Mapa de requisitos → tests

| REQ-ID | Comportamiento | Archivo test |
|--------|--------------|----|
| VSOL-01 | `_parse_onu_state()` parsea ONLINE/OFFLINE/RANGING y serial | `test_vsol_parser.py` |
| VSOL-01 | `_parse_optical_info()` extrae Rx/Tx dBm float | `test_vsol_parser.py` |
| VSOL-03 | `connect_timeout=30` en `asyncssh.connect()` | `test_vsol_collector.py` |
| VSOL-03 | SSH se cierra en finally (async with) | `test_vsol_collector.py` |
| VSOL-04 | circuit breaker abre tras 3 fallos SSH | `test_vsol_circuit_breaker.py` |
| VSOL-04 | circuit breaker bloqueado → skips SSH | `test_vsol_circuit_breaker.py` |
| VSOL-05 | `upsert_onu()` crea Device + ONU en primera ejecución | `test_vsol_collector.py` |
| VSOL-05 | `upsert_onu()` actualiza señal y estado en segunda ejecución | `test_vsol_collector.py` |
| ALERT (señal) | alerta Telegram si `signal_rx_dbm < threshold` | `test_vsol_collector.py` |
| ALERT (señal) | debounce: no reenviar alerta si clave Redis existe | `test_vsol_collector.py` |

---

## Riesgos y validación requerida

### Riesgo 1 (CRÍTICO): Formato exacto de salida CLI [MEDIUM]
**Qué puede fallar:** Las columnas de `show pon onu state` pueden tener espaciado diferente o nombres distintos en el hardware real (vs. el formato documentado arriba).
**Mitigación:** La primera ejecución debe loggear la salida raw completa de cada comando CLI. Los parsers usan regex con `.search()` (no posición de columna), lo que tolera variaciones de espaciado.
**Acción hands-on:** Ejecutar `show pon onu state gpon 0/1` en el hardware y comparar con el regex. Si falla, ajustar regex antes de activar el beat schedule.

### Riesgo 2 (ALTO): `show pon optical-info gpon 0/X onu N` solo funciona para ONLINE ONUs [HIGH]
**Qué puede fallar:** Si se ejecuta para una ONU OFFLINE, el OLT puede retornar error o colgar la sesión SSH.
**Mitigación:** Solo ejecutar `show pon optical-info` para ONUs con `state == "ONLINE"` en el resultado de `show pon onu state`. Implementado en el parser.

### Riesgo 3 (MEDIO): Límite de 3 sesiones SSH simultáneas [HIGH]
**Qué puede fallar:** Si otro proceso (técnico vía SSH manual) ya tiene 3 sesiones, el collector no puede conectar.
**Mitigación:** Circuit breaker per OLT ya maneja este caso (3 fallos → 5 min pausa). El técnico raramente tiene 3 sesiones SSH simultáneas en el OLT. Riesgo aceptable para v1.

### Riesgo 4 (MEDIO): `ip_address="0.0.0.0"` en ONUs — únicas por Device [MEDIUM]
**Qué puede fallar:** Múltiples ONUs con `ip_address="0.0.0.0"` no violan el schema, pero pueden confundir futuras consultas que asuman IP única.
**Mitigación:** Excluir ONUs de ICMP polling. Para v1, la "IP" de una ONU es irrelevante — solo se accede vía OLT. Documentado en notas del Device.

### Riesgo 5 (BAJO): asyncssh y Tailscale SOCKS5 proxy [LOW]
**Qué puede fallar:** La conectividad vía Tailscale userspace usa SOCKS5 proxy en `localhost:1055`. asyncssh necesita configuración para usar proxy.
**Mitigación:** asyncssh soporta SOCKS5 via `proxy_command` o configuración de proxy. El OLT IP `192.168.8.200` ya estaba planificado para acceder vía VPN. Validar en integración.

---

## Decisiones arquitectónicas Phase 4

| Decisión | Elección | Alternativa rechazada | Razón |
|----------|----------|----------------------|-------|
| Una sesión SSH por ciclo | Sí | 8 sesiones paralelas | Límite de 3 sesiones SSH en OLT |
| Optical poll cada 5min | Sí | Optical en cada ciclo 60s | ~400 comandos × 0.3s = 120s > 60s ciclo |
| Prefijo `vsol:` para circuit breaker | Sí | Reusar prefijo `cb:` | Evitar colisión con circuit breaker Mikrotik |
| ip_address="0.0.0.0" para ONUs | Sí | ip_address=serial o null | NOT NULL constraint; serial no es IP |
| Excluir ONU de ICMP polling | Sí | Incluir con ip_address real | ONUs no tienen IPs routeables desde NOC |
| VSOL-02 (EPON) diferido | Sí | Implementar stub | No hay hardware EPON; usuario confirmó |

---

## Fuentes

### Primarias (HIGH confidence)
- OLT backup `70b64fd8bb55.cfg` — hardware real BEEPYRED (firmware V2.3.1R, 8 GPON ports, 3 SSH sessions max)
- `asyncssh.readthedocs.io` — connect(), known_hosts, connect_timeout, conn.run()
- Codebase Phase 3: `circuit_breaker.py`, `telegram.py`, `thresholds.py` — patrones reutilizados
- Migración `001_initial_schema.py` — tablas `devices` y `onus` ya existen

### Secundarias (MEDIUM confidence)
- VSOL V2.x CLI reference — formato `show pon onu state` y `show pon optical-info` (training knowledge, no verificado contra hardware real)
- Pattern: polling task exclude por device_type — patrón SQLAlchemy estándar

---

## Log de suposiciones [ASSUMED]

| # | Claim | Riesgo si incorrecto |
|---|-------|--------------------|
| A1 | Formato columnas `show pon onu state` coincide con regex propuesto | Parser silenciosamente retorna 0 ONUs; loggear salida raw en primera ejecución |
| A2 | `show pon optical-info gpon 0/X onu N` retorna error o output vacío para ONUs OFFLINE (no cuelga la sesión) | Sesión SSH puede quedar bloqueada; mitigación: timeout=30 en `conn.run()` |
| A3 | asyncssh es compatible con `asyncio.run()` (patrón Celery ya establecido) | Conflict de event loop; alternativa: `run_in_executor` |
| A4 | El Tailscale SOCKS5 proxy aplica a asyncssh sin configuración adicional | Conexión SSH falla con "Connection refused"; necesita `proxy_command` |

## Metadata

**Fecha de investigación:** 2026-05-14
**Válido hasta:** 2026-06-14 (30 días)
**Confianza global:** HIGH para asyncssh, patrones upsert y circuit breaker; MEDIUM para CLI parsers (requieren validación hands-on)
