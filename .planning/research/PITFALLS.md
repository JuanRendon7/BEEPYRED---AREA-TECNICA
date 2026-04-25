# Domain Pitfalls — BEEPYRED NOC

**Domain:** ISP Network Operations Center — 500+ dispositivos (Mikrotik, VSOL OLT, Ubiquiti, Mimosa)
**Researched:** 2026-04-25
**Confidence overall:** HIGH (pitfalls basados en patrones bien documentados de sistemas de monitoreo de red a escala)

---

## Pitfalls Críticos

Errores que causan reescrituras o fallos en producción.

---

### Pitfall C1: Polling Concurrente Sin Control — El Thundering Herd

**Qué sale mal:**
El sistema lanza 500+ conexiones simultáneas cada 30-60 segundos. Los equipos de borde (Mikrotik de baja gama, OLTs) se saturan respondiendo polls simultáneos. El servidor NOC agota su pool de conexiones TCP. El resultado: timeouts masivos falsos que generan alertas de "todos los equipos caídos" aunque la red esté sana.

**Por qué ocurre:**
Implementación ingenua donde un `setInterval` único dispara todos los polls al mismo tiempo. Con 500 equipos y 60s de intervalo, el instante T=0 y T=60 crean "tormentas" de conexiones.

**Consecuencias:**
- CPU spike en el servidor NOC cada 60 segundos
- Mikrotiks con pocos recursos (hAP ac lite, etc.) caen bajo la carga del poll mismo
- False positives masivos — alertas de Telegram para cada equipo "caído"
- Imposible distinguir caída real de saturación del poller

**Prevención:**
- Implementar jitter aleatorio en el scheduler: cada equipo tiene su propio offset inicial aleatorio (0 a interval_ms)
- Usar una cola de trabajo (queue) con worker pool de tamaño fijo (ej. max 20 conexiones concurrentes)
- Bibliotecas: `p-limit` (Node.js) o `asyncio.Semaphore` (Python) para limitar concurrencia
- Diseño: nunca `Promise.all(todos_los_equipos)` — siempre chunks con límite

**Codigo de alerta:**
```
# PELIGROSO — dispara todo a la vez
setInterval(() => devices.forEach(d => poll(d)), 60000)

# CORRECTO — queue con concurrencia limitada
const limit = pLimit(20)
const poll = () => Promise.all(devices.map(d => limit(() => pollDevice(d))))
```

**Deteccion temprana:**
- CPU del servidor NOC con picos periódicos exactamente cada N segundos
- Logs que muestran muchos timeouts al mismo timestamp
- Tiempo total de ciclo de polling superior al intervalo configurado

**Fase que debe abordarlo:** Fase 1 (arquitectura del scheduler) — si no se diseña bien desde el inicio, refactorizar es costoso.

---

### Pitfall C2: RouterOS API — Sesiones Colgadas y Sin Timeout

**Qué sale mal:**
RouterOS API (puerto 8728/8729) permite un número limitado de sesiones concurrentes por usuario (por defecto 10 en versiones modernas, puede ser menos según versión). Si el código abre una sesión y no la cierra correctamente (por excepción, timeout de red, reinicio del servidor NOC), las sesiones quedan "abiertas" en el RouterOS. Después de N fallos, el router rechaza nuevas conexiones con "too many sessions" y el dispositivo aparece como DOWN aunque esté completamente funcional.

**Por qué ocurre:**
- Manejo de errores sin `finally` clause que cierre la sesión
- Network blips que dejan la conexión TCP en estado CLOSE_WAIT pero el RouterOS no la expira
- Keep-alive TCP no configurado, la sesión "zombie" permanece indefinidamente

**Consecuencias:**
- Equipo inaccesible vía API hasta que alguien entre manualmente y cierre sesiones (`/ip service` o reboot)
- El NOC reporta equipo DOWN cuando el equipo está perfectamente operativo
- Difícil de diagnosticar — el log del NOC muestra "connection refused" sin contexto

**Prevención:**
- Siempre usar conexiones efímeras (connect → query → disconnect) en vez de sesiones persistentes para monitoreo
- Implementar timeout explícito en el socket TCP (no solo timeout de aplicación): `socket.settimeout(10)` en Python, `timeout` option en librería Node.js
- Si se usan sesiones persistentes, implementar health check periódico y reconexión automática
- Configurar en RouterOS: `/ip service set api session-timeout=5m` para que el router expire sesiones huérfanas
- Biblioteca recomendada: `librouteros` (Python) o `node-routeros` — ambas tienen manejo de sesión, pero revisar que implementen cierre en error

**Sesiones por usuario en RouterOS:**
- RouterOS v6: limite de 10 sesiones API por defecto (configurable)
- RouterOS v7: misma restricción, ajustable vía `/ip service`
- **Confianza: MEDIUM** — los límites exactos varían por versión y configuración

**Deteccion temprana:**
- Errors "too many login sessions" o "can't connect" en logs del NOC para un equipo específico
- El equipo responde ICMP (ping OK) pero API falla
- Patrón: fallo de API comienza después de que el servidor NOC se reinicia abruptamente

**Fase que debe abordarlo:** Fase 1 (cliente RouterOS API) + documentar en runbook operativo.

---

### Pitfall C3: SSH a VSOL OLT — Buffering, Prompts y Sesiones que No Terminan

**Qué sale mal:**
Las OLTs VSOL (y la mayoría de OLTs GPON chinas) tienen implementaciones SSH no estándar con CLI interactivas. Los comandos como `show onu optical-info all` producen output paginado que espera que el usuario presione "space" o "q". Un cliente SSH automatizado que no maneja esto queda bloqueado indefinidamente esperando el siguiente prompt, nunca libera la conexión, y el poll cuelga hasta agotar el timeout.

**Problemas específicos observados en VSOL y OLTs similares:**
1. **Paginación forzada:** Output cortado con `--More--` requiere envío de espacio o configurar `terminal length 0` al inicio
2. **Prompt no estándar:** La expresión regular de detección de prompt falla — el equipo usa `VSOL#` o variantes con hostname que cambia
3. **Login banner largo:** El SSH tarda en conectar porque el banner de login es extenso; parsear el banner como respuesta al comando
4. **Eco de comandos:** El SSH de la OLT hace eco del comando enviado antes de la respuesta — hay que strippearlo del output
5. **Telnet fallback:** Algunos modelos VSOL tienen SSH roto o con timeouts agresivos; Telnet funciona mejor pero es menos seguro
6. **Conexiones que no cierran:** `channel.close()` no siempre hace que la OLT libere el recurso del lado servidor; acumula conexiones hasta que el equipo falla

**Por qué ocurre:**
Los vendors de OLT GPON de bajo costo implementan CLI sobre SSH de forma no estándar. No es un servidor SSH con shell POSIX — es una aplicación propietaria que emula una CLI de forma mínima.

**Consecuencias:**
- Polling de OLT cuelga indefinidamente sin timeout correcto
- Worker thread bloqueado no puede procesar otros dispositivos
- Si se usan threads: thread pool se llena de conexiones bloqueadas
- Datos de ONU no actualizados durante horas sin que el sistema se entere

**Prevención:**
- Siempre usar timeout estricto en la conexión SSH completa (no solo en connect): usar `asyncssh` con `command_timeout`, o `paramiko` con threading timeout
- Enviar `terminal length 0` (o equivalente VSOL) como primer comando para deshabilitar paginación
- Regex de prompt debe incluir variantes: `/[A-Za-z0-9_-]+[#>$]\s*$/`
- Parsear y descartar el eco del comando antes de procesar respuesta
- Implementar circuit breaker por equipo: si falla N veces seguidas, marcar como "unreachable" y no intentar por M minutos
- Testear con `asyncssh` en Python — mejor manejo de timeouts que paramiko puro

**Deteccion temprana:**
- Conexiones SSH a OLT en estado ESTABLISHED sin actividad (visible con `netstat` en servidor NOC)
- Worker threads "stuck" — el pool de workers siempre está al máximo ocupado
- Datos de ONU no cambian durante horas aunque la red tenga movimiento real

**Fase que debe abordarlo:** Fase 2 (integración VSOL) — diseñar la capa de abstracción SSH con timeout y circuit breaker antes de escribir parsers de CLI.

---

### Pitfall C4: Crecimiento Descontrolado del Almacenamiento de Series de Tiempo

**Qué sale mal:**
Con 500 equipos, polling cada 60 segundos, y 10-20 métricas por equipo, se generan aproximadamente **5,000-10,000 puntos de datos por minuto**. Sin retención configurable y compresión, la base de datos crece a ~500MB-2GB por día dependiendo del formato. En Railway, el almacenamiento tiene costo y límites. A los 3-6 meses, el disco se llena y el sistema falla silenciosamente (escrituras que fallan sin alertar, o alertas que no guardan historial).

**Cálculo de referencia:**
```
500 equipos x 15 métricas x 60s intervalo x 24h x 365d
= ~2,628,000,000 puntos/año

Con InfluxDB line protocol ~50 bytes/punto:
= ~131 GB/año sin compresión
Con compresión InfluxDB (~10:1): ~13 GB/año
Con downsampling agresivo: ~1-2 GB/año
```

**Problemas de cardinalidad (InfluxDB específico):**
Si se usan tags con alta cardinalidad (ej. `interface_name` como tag con 50 interfaces por equipo x 500 equipos = 25,000 series únicas), InfluxDB crea índices masivos en memoria. Puede causar OOM del proceso influxd.

**Por qué ocurre:**
- No se configura retención de datos (retention policy) desde el inicio
- Se almacenan métricas de alta frecuencia para siempre sin downsampling
- Se usan campos de alta cardinalidad como tags en lugar de fields

**Consecuencias:**
- Disco lleno en semanas en lugar de años
- Queries lentas a medida que crecen los datos
- Costo de Railway se dispara por almacenamiento
- Sistema cae silenciosamente cuando las escrituras fallan por espacio

**Prevención:**
- Definir retención desde el día 1: datos raw 7-15 días, datos downsampleados (1min→1h) 90 días, datos diarios 1 año
- Para InfluxDB: configurar Continuous Queries o Tasks de downsampling automático
- Para TimescaleDB: usar `add_retention_policy()` y `add_continuous_aggregate()`
- Regla de cardinalidad: nunca usar como TAG algo con más de ~1000 valores únicos
- Interfaces de red: guardar como field, no como tag
- Monitorear el tamaño de la DB como métrica del propio NOC (alertar si crece >X GB/semana)
- Alternativa sencilla para v1: SQLite con tabla de métricas + cron de purga de datos >30 días — suficiente para comenzar sin overhead operacional de InfluxDB

**Deteccion temprana:**
- Tiempo de respuesta de queries aumenta semana a semana
- `df -h` en el servidor Railway muestra crecimiento lineal sin plateau
- Queries de "últimos 30 días" tardan segundos cuando antes tardaban milisegundos

**Fase que debe abordarlo:** Fase 1 (diseño de schema de datos) — la retención es casi imposible de agregar retroactivamente sin migración costosa.

---

### Pitfall C5: Alertas Ruidosas — Alert Fatigue que Invalida el NOC

**Qué sale mal:**
El sistema envía alertas por Telegram cada vez que un equipo no responde a un único poll. Con 500 equipos y conectividad variable (radioenlaces que fluctúan, Mikrotik que reinicia actualizaciones automáticas, OLTs que demoran en responder), el técnico recibe decenas de alertas falsas por hora. En menos de una semana, el técnico ignora las notificaciones de Telegram — el NOC pierde su propósito principal.

**Escenarios reales de false positives en este dominio:**
- Mikrotik reiniciando tras actualización de firmware: aparece DOWN 2-3 minutos, genera alerta, vuelve solo
- Radioenlace Ubiquiti/Mimosa con interferencia momentánea: packet loss 30 segundos, no es un incidente real
- VSOL OLT SSH timeout por carga: equipo OK pero CLI no responde en tiempo límite
- Network blip en el camino al equipo (no en el equipo mismo): 1-2 polls fallidos
- El propio servidor NOC tiene jitter de red: poll falla por latencia alta, no por equipo caído

**Por qué ocurre:**
Lógica de alerta tipo "si falla 1 poll → alertar". Sin ventana de confirmación ni suppression.

**Consecuencias:**
- Alert fatigue: el técnico silencia las notificaciones de Telegram
- Incidentes reales se pierden en el ruido
- El NOC pierde credibilidad ("siempre está dando falsas alarmas")
- Imposible usar el historial de incidentes para análisis real

**Prevención:**
- **Nunca alertar en el primer fallo.** Mínimo 2-3 polls fallidos consecutivos antes de disparar alerta
- Implementar estados de transición: UP → DEGRADED (1 fallo) → DOWN (3 fallos consecutivos) → alerta
- Flap detection: si un equipo sube y baja en <5 minutos, suprimir alertas adicionales y enviar solo "equipo inestable"
- Alert cooldown: no re-alertar si ya se envió alerta en los últimos N minutos (ej. 15 min)
- Alert on recovery: cuando vuelve, enviar "equipo recuperado" con duración del incidente
- Umbrales para métricas (CPU, señal): usar promedio móvil de 3-5 muestras, no valor puntual
- Para radioenlaces: permitir umbrales de señal más tolerantes (la señal fluctúa naturalmente)

**Deteccion temprana:**
- Si el sistema envía >5 alertas/hora en condiciones normales de red, algo está mal en la lógica de alertas
- El técnico dice "ya no miro el Telegram del NOC"

**Fase que debe abordarlo:** Fase 1 (diseño del motor de alertas) — agregar lógica de debounce después es más difícil que diseñarla desde el inicio.

---

### Pitfall C6: Railway — Estado Efímero y Ausencia de Filesystem Persistente

**Qué sale mal:**
Railway es una plataforma PaaS con deployments inmutables. Cada redeploy (por push de código, por restart automático, por update de Railway) crea un nuevo contenedor con filesystem vacío. Cualquier dato escrito en disco durante la ejecución (base de datos SQLite, archivos de configuración, logs, uploads) **se pierde completamente** en el próximo redeploy.

**Casos concretos de este proyecto:**
- SQLite almacenando métricas históricas: se borra en cada deploy → historial de incidentes perdido
- Archivos de configuración de equipos generados en runtime: se borra en deploy → NOC no sabe qué equipos monitorear
- Caché local de estado de ONUs: se borra → el primer ciclo post-deploy reporta todos como UP (estado desconocido)
- Logs en filesystem: se borran → no hay evidencia de problemas anteriores

**Por qué ocurre:**
Railway por defecto no persiste el filesystem entre deployments. Los Volumes de Railway son la solución, pero deben configurarse explícitamente con un mount point. Muchos proyectos los ignoran hasta que pierden datos en producción.

**Consecuencias:**
- Pérdida total de datos históricos en cada deploy — el NOC "olvida" todo
- Si el inventario de equipos está en JSON local: se pierde la configuración
- Si el estado de alertas está en memoria/disco: se reinician todos los contadores de flap detection

**Prevención:**
- **Nunca usar SQLite en filesystem local para datos que deben persistir** — usar base de datos externa desde el día 1
- Opciones persistentes compatibles con Railway:
  - Railway PostgreSQL add-on (recomendado: gratis en tier básico, persiste entre deploys)
  - Railway Redis add-on para estado en tiempo real (contadores de polls fallidos, estado de alerta)
  - TimescaleDB en Railway o externo (Supabase, Neon) para series de tiempo
  - InfluxDB Cloud (tier gratuito) para métricas — fuera del contenedor Railway
- Si se usa Railway Volume: montar en `/data` y apuntar todas las escrituras ahí, pero Railway Volumes tienen limitaciones (no accesibles entre múltiples instancias)
- Variables de entorno para configuración: nunca escribir config en archivos locales
- El inventario de equipos debe vivir en la base de datos, no en un JSON en disco

**Deteccion temprana:**
- Después de un deploy, el dashboard muestra "sin datos históricos"
- Los contadores de equipos DOWN se reinician a 0 después de cada deploy
- Alertas de Telegram envían "equipo recuperado" para todos los equipos tras cada deploy (porque el estado se reinicia)

**Fase que debe abordarlo:** Fase 0 (infraestructura base) — decidir la arquitectura de persistencia antes de escribir una línea de código de negocio.

---

## Pitfalls Moderados

---

### Pitfall M1: Ubiquiti AirOS SSH — Comandos No Estandarizados por Firmware

**Qué sale mal:**
Ubiquiti tiene múltiples líneas de producto (AirMax, AirFiber, LTU, Wave) con diferentes versiones de AirOS (6.x, 8.x) y algunos en UNMS/UISP con API REST. Los comandos SSH para obtener señal (`iwconfig`, `ubntbox`, `mca-status`) varían según versión de firmware. Un parser que funciona en AirOS 6.1 puede no funcionar en AirOS 8.7. Con radioenlaces en campo que tienen firmwares heterogéneos, el NOC puede tener parsers rotos en 30-40% de los equipos.

**Prevención:**
- Preferir UISP API REST cuando esté disponible (UISP/UNMS gestiona los equipos registrados en él)
- Para SSH directo: detectar versión de firmware y seleccionar parser correcto
- Diseñar parsers con fallback: si falla el parser primario, intentar alternativa, y si ambos fallan, marcar dato como "unavailable" en vez de crashear
- Mantener inventario con versión de firmware de cada equipo para saber qué parser usar

**Deteccion temprana:**
- Métricas de señal de algunos Ubiquiti siempre en NULL o 0 mientras otros funcionan bien
- Patrón: los problemas se agrupan por modelo de equipo o rango de versión de firmware

**Fase que debe abordarlo:** Fase 3 (integración Ubiquiti).

---

### Pitfall M2: Mimosa API REST — Autenticación por Cookie y Sesión Local

**Qué sale mal:**
Los equipos Mimosa (B5, A5x) tienen una API REST local accesible directamente en la IP del equipo. La autenticación no usa Bearer tokens estándar — usa cookies de sesión que expiran. Si el código no renueva la cookie o no maneja el 401, la sesión expira silenciosamente y el equipo empieza a retornar errores de autenticación que se interpretan como DOWN.

**Prevención:**
- Implementar reautenticación automática al detectar 401/403
- No asumir que una cookie de Mimosa dura más de la sesión actual
- Testear timeout de sesión de cada modelo Mimosa específico que tiene BEEPYRED
- Alternativa: SNMP en Mimosa si la API local es inestable (Mimosa soporta SNMP v2c)

**Fase que debe abordarlo:** Fase 4 (integración Mimosa).

---

### Pitfall M3: Conectividad del Servidor NOC a Equipos en Red Privada

**Qué sale mal:**
Los equipos (Mikrotik, VSOL) están en la red privada de BEEPYRED. El servidor NOC en Railway está en internet. Sin una ruta de acceso explícita, el servidor NOC no puede hacer poll de los equipos. Esto no es un bug — es una restricción de arquitectura que si no se resuelve antes de comenzar el desarrollo, todo el trabajo de integración no puede probarse en producción.

**Opciones de acceso:**
1. Mikrotik como gateway con IP pública y NAT/firewall para permitir acceso desde Railway a la red interna
2. VPN (WireGuard en Mikrotik) — el servidor Railway se conecta como cliente VPN
3. Equipos core con IP pública directa
4. Agente local en la red del ISP que hace el polling y envía datos al NOC en Railway (arquitectura hub-and-spoke)

**Por qué es un pitfall:**
Muchos proyectos NOC comienzan el desarrollo sin resolver esto, y en el primer deploy a Railway descubren que nada puede hacer poll. La arquitectura hub-and-spoke (agente local) es la más robusta pero duplica la complejidad: dos componentes desplegados en lugar de uno.

**Prevención:**
- Resolver el acceso de red como prerequisito de Fase 1, no como afterthought
- Documentar en PROJECT.md la topología de acceso elegida
- Desarrollar desde el inicio contra IPs reales (con VPN local durante desarrollo)

**Fase que debe abordarlo:** Pre-Fase 1 (infraestructura de acceso) — bloquea todo lo demás.

---

### Pitfall M4: SNMP Community Strings por Defecto en VSOL OLT

**Qué sale mal:**
Los dispositivos VSOL tienen SNMP habilitado por defecto con community string "public". Si el proyecto usa SNMP (aunque sea secundariamente), hay riesgo de exposición si la OLT tiene IP pública o accesible desde internet. No es un bug del NOC, pero el NOC puede crear una falsa sensación de seguridad al "tener monitoreo" sin revisar la superficie de ataque.

**Prevención:**
- Al desplegar cualquier integración SNMP: cambiar community strings y restringir a source IP del servidor NOC
- Este pitfall es menor para v1 si se usa SSH sobre SNMP, pero debe estar en el checklist de hardening

**Fase que debe abordarlo:** Fase 2 (antes de ir a producción con VSOL).

---

## Pitfalls Menores

---

### Pitfall m1: Telegram Bot Rate Limiting

**Qué sale mal:**
La API de Telegram limita a 30 mensajes por segundo a diferentes usuarios, y 20 mensajes por minuto al mismo chat. Si hay un outage masivo (ej. cae el uplink principal y 200 equipos aparecen como DOWN simultáneamente), el NOC intenta enviar 200 alertas de Telegram en segundos — Telegram empieza a rechazar mensajes con 429 Too Many Requests. Las alertas más importantes (equipos core) pueden perderse porque la cola se llena de alertas de dispositivos hoja.

**Prevención:**
- Implementar agrupación de alertas: "X equipos caídos en los últimos 2 minutos" en lugar de X mensajes separados
- Priorizar alertas: equipos core (OLTs, routers de uplink) tienen prioridad sobre ONUs individuales
- Cola de alertas con rate limiting propio: max 1 mensaje cada 3 segundos
- Para outages masivos: enviar resumen cada 5 minutos, no alerta individual por equipo

**Fase que debe abordarlo:** Fase 1 (motor de alertas).

---

### Pitfall m2: ONUs GPON — Datos Obsoletos Sin Señal de Invalidación

**Qué sale mal:**
Las OLTs VSOL reportan el estado de las ONUs en un solo comando (`show onu state all` o similar). Si la OLT no responde (SSH timeout), el NOC muestra los últimos datos conocidos de las ONUs como si fueran actuales. Un técnico puede ver "ONU UP, señal -23 dBm" cuando en realidad la ONU lleva 2 horas caída porque la OLT no pudo consultarse.

**Prevención:**
- Mostrar timestamp de última actualización junto a cada dato de ONU
- Si los datos tienen más de 2x el intervalo de polling de antigüedad: mostrar indicador "datos obsoletos" en el dashboard
- Distinguir "equipo DOWN" de "datos no disponibles" — son estados diferentes

**Fase que debe abordarlo:** Fase 2 (integración VSOL) + Fase 5 (UI/dashboard).

---

### Pitfall m3: Mikrotik RouterOS v7 vs v6 — Diferencias en Comandos API

**Qué sale mal:**
RouterOS v7 (disponible desde 2021, adoptado gradualmente) tiene cambios en algunos comandos API. Si la red de BEEPYRED tiene equipos con v6 y v7 mezclados (probable en una red de 500 equipos que creció orgánicamente), el código que funciona para v6 puede retornar datos incorrectos o errores en v7, especialmente en interfaces y BGP.

**Diferencias conocidas:**
- WireGuard es nativo en v7, no existe en v6
- Algunos paths de API cambiaron (ej. `/interface/ethernet` tiene nuevos campos en v7)
- El soporte de IPv6 mejoró en v7 con nuevos endpoints

**Prevención:**
- Al conectar a cada Mikrotik, leer la versión de ROS (`/system resource get version`)
- Diseñar adaptadores por versión si es necesario, o usar solo comandos comunes a v6 y v7
- Inventariar la distribución de versiones de la red antes de iniciar desarrollo

**Fase que debe abordarlo:** Fase 1 (cliente RouterOS API).

---

### Pitfall m4: Timezone y Timestamps en Multi-Equipo

**Qué sale mal:**
Los Mikrotik y OLTs VSOL pueden tener configurada la hora del sistema incorrectamente (sin NTP, o con timezone erróneo). Los logs y eventos que el NOC muestra tienen timestamps desincronizados con la realidad. El técnico ve "equipo cayó a las 3pm" cuando en realidad cayó a las 6pm.

**Prevención:**
- Nunca confiar en el timestamp del equipo para registrar incidentes — usar el timestamp del servidor NOC (UTC) al momento de detectar el fallo
- Si se usa el timestamp del equipo (ej. para correlación de logs): advertir en UI que es el reloj del equipo, no el tiempo real
- Almacenar todo en UTC; convertir a timezone local solo en la UI

**Fase que debe abordarlo:** Fase 1 (modelo de datos de incidentes).

---

## Tabla de Fases y Pitfalls

| Fase / Área | Pitfall Principal | Acción Requerida |
|-------------|------------------|------------------|
| Pre-Fase 1: Infraestructura | M3: Conectividad NOC a equipos privados | Definir y validar arquitectura de acceso antes de cualquier desarrollo |
| Fase 0: Persistencia | C6: Railway filesystem efímero | Usar PostgreSQL externo desde el inicio; nunca SQLite local |
| Fase 1: Scheduler | C1: Thundering herd polling | Implementar queue con concurrencia limitada + jitter aleatorio |
| Fase 1: RouterOS API | C2: Sesiones API colgadas | Cliente con timeout, cierre en `finally`, session-timeout en ROS |
| Fase 1: Alertas | C5: Alert fatigue | Lógica de debounce (N fallos consecutivos) + flap detection |
| Fase 1: Alertas | m1: Telegram rate limiting | Agrupación de alertas + priorización por tipo de equipo |
| Fase 1: Modelo de datos | C4: Crecimiento de TSDB | Definir retención y downsampling desde el schema inicial |
| Fase 1: Modelo de datos | m4: Timestamps erróneos | Usar timestamp del NOC en UTC para incidentes |
| Fase 1: RouterOS API | m3: ROS v6 vs v7 | Detectar versión al conectar; usar comandos compatibles |
| Fase 2: VSOL Integration | C3: SSH OLT bloqueante | asyncssh con timeout + circuit breaker + deshabilitar paginación |
| Fase 2: VSOL Integration | m2: Datos obsoletos de ONUs | Mostrar timestamp de última actualización; marcar datos stale |
| Fase 2: VSOL Integration | M4: SNMP community strings | Cambiar "public" y restringir source IPs antes de producción |
| Fase 3: Ubiquiti | M1: Parsers heterogéneos por firmware | Detectar firmware version; parsers con fallback |
| Fase 4: Mimosa | M2: Cookie de sesión que expira | Reautenticación automática en 401/403 |

---

## Fuentes

- Análisis del dominio: patrones comunes en implementaciones de NOC/NMS para ISPs documentados en issues de proyectos como Oxidized, LibreNMS, Zabbix community
- RouterOS API: documentación oficial MikroTik Wiki (limitaciones de sesiones concurrentes)
- Railway: documentación oficial Railway (comportamiento de filesystem efímero y Volumes)
- InfluxDB: documentación oficial sobre cardinalidad y retention policies
- Telegram Bot API: documentación oficial (rate limits)
- **Confianza:** Pitfalls C1-C6 son HIGH (patrones ampliamente documentados). M1-M4 son MEDIUM (requieren validación contra versiones específicas del hardware de BEEPYRED). m1-m4 son MEDIUM-HIGH.

**Nota de validación requerida:** Los límites exactos de sesiones RouterOS API y el comportamiento específico de SSH en los modelos VSOL que tiene BEEPYRED deben verificarse conectando a un equipo real en Fase 1/2 respectivamente. El comportamiento puede variar entre modelos VSOL (V1600D, V1600G, etc.).
