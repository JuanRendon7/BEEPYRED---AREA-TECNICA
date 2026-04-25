# Project Research Summary

**Project:** BEEPYRED NOC — Network Operations Center para ISP
**Domain:** ISP Network Operations Center — 500+ dispositivos heterogeneos (Mikrotik, VSOL OLT/GPON, Ubiquiti, Mimosa)
**Researched:** 2026-04-25
**Confidence:** HIGH (stack y arquitectura), MEDIUM (integraciones VSOL y Mimosa especificas por modelo)

## Executive Summary

BEEPYRED NOC es una plataforma de monitoreo de red interna que resuelve un problema de visibilidad fragmentada: el tecnico actualmente debe entrar a cada equipo por separado para saber si esta caido o degradado. El patron de construccion correcto para este dominio es un monolito modular con worker de polling asicrono, siguiendo arquitecturas establecidas como LibreNMS y Zabbix, pero sin la complejidad operacional de microservicios. Python 3.12 + FastAPI + Celery sobre Railway es el stack recomendado, con integraciones nativas por fabricante: RouterOS API para Mikrotik, asyncssh para VSOL OLT, UISP/REST para Ubiquiti, y REST local para Mimosa. SNMP no es el protocolo primario en ningun caso, tal como establece PROJECT.md.

El riesgo tecnico principal no es el stack ni el frontend: es la capa de integracion con los equipos de red. Los colectores de VSOL OLT via SSH son los de mayor complejidad — salida CLI sin estructura, paginacion interactiva, prompts no estandar, parsers que varian por modelo y firmware — y se les deben destinar 2-3 dias solo de investigacion contra el hardware real antes de escribir el codigo. Igual de critica es la conectividad de red: el worker en Railway corre en internet pero los equipos estan en la red privada del ISP. Esta restriccion arquitectonica debe resolverse como prerequisito absoluto antes de escribir cualquier linea de codigo de negocio. Si no se resuelve primero, todo el trabajo de integracion no puede probarse en produccion.

La secuencia de construccion correcta es: infraestructura y acceso de red primero, luego pipeline base con ICMP ping para validar el ciclo completo, luego collectors por fabricante empezando por Mikrotik (el mas documentado), y finalmente el frontend sobre datos reales. Construir el dashboard antes de tener datos reales de los equipos es el anti-patron mas comun en proyectos NOC y produce reescrituras costosas. Las alertas Telegram requieren logica de debounce desde el primer dia — sin ella, el alert fatigue invalida el NOC en la primera semana de uso real.

---

## Key Findings

### Recommended Stack

Python domina en automatizacion de redes porque las bibliotecas criticas son Python-nativas: `librouteros` para RouterOS API no tiene equivalente mantenido en Node.js; `asyncssh` y `paramiko` para SSH a OLTs son Python-only y maduros. asyncio maneja 500+ conexiones I/O-bound concurrentes sin hilos, con el patron `asyncio.Semaphore(50)` que limita a 50 conexiones simultaneas maximas — el ciclo de 500 equipos completa en 20-50 segundos dentro del intervalo de 60 segundos.

**Core technologies:**

- **Python 3.12 + FastAPI 0.111+:** Runtime y framework web. Async-first, SSE nativo, Pydantic v2 para validacion de respuestas de dispositivos. Elegido sobre Flask/Django (sincronos) y Node.js (sin RouterOS API library).
- **Celery 5.3+ + Redis 7.2:** Worker de polling concurrente con Celery Beat como scheduler. Redis actua como broker de tareas, cache de ultimo estado (TTL 60s) y bus pub/sub entre worker y web service. Escala workers independientemente del web service.
- **asyncio + asyncssh 2.14+:** Polling I/O-bound concurrente sin hilos. Critico para SSH a OLTs VSOL sin bloquear el event loop.
- **librouteros 3.2+:** RouterOS API nativo Python (puerto 8728/8729). Datos estructurados, evita parseo de texto SSH para Mikrotik.
- **aiohttp 3.9+:** HTTP client async para UISP API (Ubiquiti) y Mimosa REST API.
- **PostgreSQL 16 con particionamiento por mes:** 500 equipos x 2 polls/min x 24h = ~1.44M rows/dia. PostgreSQL estandar con particion RANGE + indice BRIN es suficiente a esta escala sin TimescaleDB (que no esta garantizado en Railway managed Postgres en todos los tiers).
- **SSE (Server-Sent Events):** Preferido sobre WebSocket para v1 porque el dashboard es primariamente lectura. Mas simple, reconexion automatica del browser nativa, sin overhead de estado bidireccional. WebSocket se reserva para v2 si se agrega control remoto.
- **React 18 + Vite 5 + shadcn/ui + Recharts + TanStack Query:** SPA interno sin SSR. TanStack Query para cache del servidor. Recharts para graficas de tendencia 24h. Next.js descartado — SSR sin valor para herramienta interna sin SEO.
- **JWT + python-jose + passlib:** Auth single-user para v1 con OAuth2 password flow canonico de FastAPI. Expandible a multi-usuario en v2 sin reescritura.
- **python-telegram-bot 21+:** Alertas Telegram async-native. Flujo: worker detecta fallo → escribe incidente en DB → llama API Telegram (fire-and-forget) → publica en Redis → FastAPI SSE → browser.
- **Docker multi-stage + Railway:** 3 servicios del mismo Dockerfile (web, worker, beat) + addons PostgreSQL y Redis. Layout minimo de mantenimiento.

**Detalles completos:** `.planning/research/STACK.md`

---

### Expected Features

El valor central del NOC es correlacion de capas: cuando cae un router Mikrotik upstream, el tecnico debe ver la causa raiz, no 50 alertas independientes de ONUs y radioenlaces downstream. Las features se organizan en dos prioridades para v1:

**Prioridad 1 — Core NOC (v1 indispensable):**
- Inventario manual de equipos (nombre, IP, tipo, zona/sitio)
- Polling ICMP ping universal como base de estado UP/DOWN para todos los equipos
- Dashboard unificado con semaforo por equipo (estado + timestamp de ultima verificacion)
- Alertas Telegram al caer y al recuperar (con duracion total del incidente)
- Historial de incidentes (quien cayo, cuando, cuanto duro)
- Autenticacion de un solo usuario (JWT)
- Metricas Mikrotik: CPU, RAM, trafico por interfaz via RouterOS API
- Metricas OLT VSOL: ONUs online/offline + Rx dBm via SSH
- Metricas Ubiquiti: Signal dBm + CCQ via UISP API o AirOS SSH
- Metricas Mimosa: RSSI + throughput via REST API local
- Pagina de detalle por equipo con historico 24h y graficas de tendencia

**Diferenciadores en v1 (si el tiempo lo permite):**
- Filtro por zona/sitio en dashboard
- Busqueda rapida de equipo u ONU
- Modo mantenimiento (silencio temporal de alertas con duracion)
- Umbral de senal configurable por equipo (warning/critical en dBm)
- Export CSV de incidentes

**Diferir a v2:**
- Correlacion de fallas en cascada (topologia de dependencias padre → hijo)
- Mapa topologico interactivo (Leaflet.js con coordenadas GPS)
- Vista jerarquica OLT → puertos PON → ONUs completa
- BGP/OSPF status en Mikrotik
- Historico de senal optica 30 dias + alertas por degradacion gradual
- Integracion Wisphub CRM

**Anti-features explicitas (NO construir en v1):**
- Control remoto de equipos — radio de falla demasiado alto para v1
- Roles y permisos multi-usuario — single user en v1
- Provisionamiento de ONUs desde el NOC — solo lectura
- App movil nativa — web responsive + alertas Telegram cubre el caso
- Monitoreo SNMP masivo — las APIs nativas dan mas datos con mejor estructura
- Autodescubrimiento de red automatico — inventario manual o importacion CSV

**Detalles completos:** `.planning/research/FEATURES.md`

---

### Architecture Approach

Monolito modular deployado en Railway como 3 servicios del mismo Dockerfile (web, worker, beat). La decision arquitectonica central es el **Protocol Adapter Pattern** para la capa de colectores: cada fabricante tiene su propia clase (`MikrotikCollector`, `VSOLCollector`, `UbiquitiCollector`, `MimosaCollector`) que implementa la misma interfaz `BaseCollector` y retorna un `DeviceMetrics` normalizado. El worker nunca sabe que protocolo usa — solo llama `collect()` y recibe datos estandarizados. Agregar un nuevo fabricante requiere una clase nueva y un entry en el registry, sin tocar el resto del sistema.

El flujo de datos es: Celery Beat encola tarea cada 30s por device activo → Worker selecciona collector via registry → `health_check()` rapido → `collect()` completo → escribe metrics a PostgreSQL → actualiza `last_seen` en devices → publica en Redis pub/sub → FastAPI SSE → browser actualiza dashboard. Las alertas se evaluan como post-poll hook dentro del worker.

**Major components:**

1. **Web Service (FastAPI):** Sirve REST API e inventario, mantiene conexiones SSE activas, autentica requests. Lee de PostgreSQL y hace bridge de Redis pub/sub al browser via SSE.
2. **Worker Service (Celery + gevent pool):** Ejecuta polling concurrente de 500 dispositivos con pool de 100+ workers gevent (I/O-bound, no CPU-bound). Normaliza metricas via collectors, escribe a DB, publica updates a Redis.
3. **Celery Beat (Scheduler):** Genera tareas de polling cada 30s por device activo. Persiste schedule en Redis, sobrevive reinicios del proceso.
4. **Collector Layer (Protocol Adapter Pattern):** Una clase por fabricante. Abstrae protocolo. Retorna `DeviceMetrics` estandarizado. El colector VSOL es el mas complejo por parseo CLI SSH.
5. **Alert Engine (post-poll hook):** Evalua umbrales tras cada poll con logica de debounce (N fallos consecutivos), genera alerts con deduplicacion, dispara Telegram con agrupacion de alertas.
6. **Redis:** Triple rol — broker Celery, cache de ultimo estado por device (TTL 60s), bus pub/sub worker → SSE.
7. **PostgreSQL:** Fuente de verdad. Schema: `devices`, `metrics` (particionada por mes), `alerts`, `incidents`, `onus`. Credenciales de dispositivos encriptadas con Fernet, clave en variable de entorno Railway.
8. **Browser SPA (React):** Dashboard read-only. SSE client con reconexion automatica nativa del browser. Al cargar: GET /api/devices desde Redis cache (respuesta <5ms). Actualizaciones push via SSE conforme llegan los polls.

**Detalles completos:** `.planning/research/ARCHITECTURE.md`

---

### Critical Pitfalls

Los siguientes pitfalls deben abordarse en las fases indicadas; ignorarlos causa reescrituras o fallos en produccion:

1. **Conectividad NOC a equipos en red privada (bloqueante pre-Fase 1):** Railway corre en internet; los equipos estan en la red privada del ISP. Sin ruta de acceso definida antes de comenzar, ninguna integracion puede probarse en produccion. Opciones: VPN WireGuard desde Railway al Mikrotik core, IP publica con firewall en equipos core, o Celery worker on-premises que empuja datos al web service en Railway. Esta decision debe tomarse antes de escribir codigo.

2. **Thundering herd en polling (Fase 1):** Lanzar 500 conexiones simultaneas cada 30s satura los equipos de borde y genera falsos DOWN masivos. Prevencion desde el inicio: `asyncio.Semaphore(50)` + jitter aleatorio en el offset inicial de cada device. Nunca `asyncio.gather(*todos_los_equipos)` sin limite.

3. **Alert fatigue por debounce insuficiente (Fase 1):** Alertar en el primer poll fallido garantiza docenas de falsas alarmas por hora. El tecnico silencia Telegram en una semana y el NOC pierde su proposito. Prevencion: maquina de estados UP → DEGRADED (1 fallo) → DOWN (3 fallos consecutivos) + flap detection + cooldown de 15 minutos entre alertas del mismo equipo.

4. **SSH a VSOL OLT bloqueante sin timeout (Fase 3):** Las OLTs VSOL tienen CLI SSH propietaria con paginacion (`--More--`), prompts no estandar, eco de comandos y latencia de 2-5s por comando. Sin timeout estricto en cada operacion, los workers se bloquean indefinidamente y el pool queda lleno de conexiones colgadas. Prevencion: `asyncssh` con `command_timeout`, primer comando `terminal length 0`, circuit breaker por equipo (skip 5 min tras 3 fallos consecutivos).

5. **Railway filesystem efimero (Pre-Fase 1):** Todo dato escrito en disco se pierde en cada redeploy. Nunca SQLite local. Todo en PostgreSQL managed addon desde el dia 1. El inventario de equipos, historial de incidentes y estado de alertas deben vivir en la DB, no en archivos locales.

6. **Sesiones RouterOS API colgadas (Fase 2):** RouterOS permite ~10 sesiones API concurrentes por usuario por defecto. Sin cierre correcto en `finally` o timeout de socket, las sesiones zombie acumulan hasta que el router rechaza nuevas conexiones y aparece como DOWN estando funcional. Prevencion: conexiones efimeras por poll, timeout de socket explicito, `session-timeout=5m` configurado en el RouterOS.

7. **Crecimiento de almacenamiento sin retencion (Pre-Fase 1, esquema):** 500 equipos x 15 metricas x 60s = gigabytes en semanas sin politica de retencion. Definir desde el schema inicial: datos raw 7-15 dias, particionamiento PostgreSQL por mes (purga via `DROP TABLE metrics_YYYY_MM`, no DELETE masivos).

**Detalles completos:** `.planning/research/PITFALLS.md`

---

## Implications for Roadmap

La arquitectura tiene dependencias de datos claras que dictan el orden de construccion. El principio rector: tener datos reales de los equipos antes de construir el frontend. El collector layer es el nucleo de valor — todo lo demas depende de el.

### Phase 0: Infraestructura, Acceso de Red y Schema Base

**Rationale:** Prerequisito absoluto. Sin persistencia externa y sin conectividad resuelta, nada puede probarse en produccion. Esta fase no produce features visibles al usuario pero desbloquea todo lo demas.
**Delivers:** Schema PostgreSQL inicial (`devices`, `metrics`, `alerts`, `incidents`, `onus`), proyecto Railway configurado (web + worker + beat + postgres + redis), estrategia de conectividad documentada y validada (VPN WireGuard, IP publica, o agente local), politica de retencion de metricas definida en el schema.
**Avoids:** C6 (Railway filesystem efimero — nunca SQLite), M3 (conectividad bloqueante — el pitfall mas critico, sin esto nada funciona), C4 (crecimiento de storage sin control — definir retencion desde el schema).
**Research flag:** Requiere decision de topologia especifica de BEEPYRED antes de comenzar. No hay patron unico — depende de si los Mikrotik core tienen IP publica o si se necesita VPN. Reunion con el tecnico necesaria antes de esta fase.

---

### Phase 1: Foundation — Inventario, Auth y Polling Base ICMP

**Rationale:** Con infraestructura lista, el siguiente paso es validar el pipeline completo (scheduler → worker → DB → SSE → browser) con el protocolo mas simple posible: ICMP ping. Esto produce valor inmediato (el tecnico sabe que esta caido) y valida la arquitectura antes de agregar complejidad de protocolo.
**Delivers:** CRUD de inventario de equipos en UI, autenticacion JWT single-user, polling ICMP de todos los equipos en la DB, dashboard con estado UP/DOWN basico (semaforo), alertas Telegram con logica de debounce (3 fallos consecutivos), historial de incidentes.
**Addresses:** Dashboard unificado, estado UP/DOWN, alertas Telegram al caer/recuperar, historial de incidentes, autenticacion basica.
**Avoids:** C1 (thundering herd — Semaphore desde el inicio), C5 (alert fatigue — debounce desde el dia 1), m4 (timestamps — usar UTC del servidor NOC, no del equipo), m3 (ROS v6/v7 — detectar version al conectar), m1 (Telegram rate limiting — agrupacion de alertas desde el inicio).
**Research flag:** Patrones bien documentados. No necesita research-phase adicional.

---

### Phase 2: Mikrotik Collector — Metricas Ricas RouterOS API

**Rationale:** Mikrotik es el fabricante con mejor documentacion y la biblioteca mas madura (`librouteros`). Empezar aqui valida el Protocol Adapter Pattern con el caso mas favorable antes de enfrentar colectores SSH complejos. Los Mikrotik son los equipos mas numerosos y criticos de la red ISP.
**Delivers:** `MikrotikCollector` completo, metricas CPU/RAM/interfaces/trafico via RouterOS API, pagina de detalle por equipo con historico 24h, graficas de tendencia (Recharts), deteccion de version ROS v6/v7.
**Addresses:** Indicadores Mikrotik CPU/RAM, trafico por interfaz, estado de interfaces, uptime.
**Avoids:** C2 (sesiones RouterOS API colgadas — cierre en finally, timeout de socket, session-timeout en ROS), m3 (v6 vs v7 — detectar version al conectar, comandos compatibles con ambas).
**Research flag:** Alta confianza en la API. Validar en Fase 2 el limite de sesiones concurrentes con un Mikrotik real de BEEPYRED antes de conectar todos los equipos.

---

### Phase 3: VSOL OLT Collector — SSH/CLI Parsing

**Rationale:** El colector mas complejo del proyecto. SSH a CLI propietaria con output no estructurado, paginacion, prompts variables y latencia alta. Se construye despues de validar el framework con Mikrotik para no mezclar la complejidad del dominio con la del framework.
**Delivers:** `VSOLCollector` con parseo estructurado de output CLI, estado de ONUs por puerto PON, senal Rx dBm por ONU, tabla `onus` actualizada en DB, indicador de "datos obsoletos" cuando el poll de la OLT falla.
**Addresses:** Estado ONUs GPON (Rx dBm, online/offline), estado de puertos PON, alarmas activas OLT.
**Avoids:** C3 (SSH bloqueante — asyncssh con command_timeout, terminal length 0, circuit breaker), m2 (datos obsoletos de ONUs — mostrar timestamp de ultima actualizacion), M4 (SNMP community strings VSOL — cambiar "public" y restringir source IPs antes de produccion).
**Research flag:** REQUIERE validacion hands-on antes de implementar. Los comandos CLI exactos varian por modelo VSOL (V1600D, V1600G, V1800) y version de firmware. Presupuestar 2-3 dias de investigacion contra los equipos reales de BEEPYRED. Sin esto, hay riesgo alto de reescritura del parser.

---

### Phase 4: Ubiquiti y Mimosa Collectors

**Rationale:** Una vez el framework de colectores esta probado con Mikrotik y VSOL, los colectores REST son mas rapidos de implementar. Ubiquiti y Mimosa tienen APIs documentadas con datos estructurados — complejidad moderada comparada con VSOL.
**Delivers:** `UbiquitiCollector` (UISP API preferida, SSH AirOS como fallback), `MimosaCollector` (REST API local), metricas de senal y throughput en dashboard, paginas de detalle para radioenlaces.
**Addresses:** Ubiquiti signal dBm + CCQ, Mimosa RSSI + throughput, estado de radioenlaces.
**Avoids:** M1 (parsers Ubiquiti heterogeneos por firmware — detectar version de firmware, parsers con fallback), M2 (Mimosa cookie de sesion que expira — reautenticacion automatica en 401/403).
**Research flag:** Confirmar antes de Fase 4: (1) si BEEPYRED tiene UISP/UNMS desplegado — si si, la integracion Ubiquiti es REST simple y mucho mas rapida; (2) version de firmware de los Mimosa en produccion (B5, A5x) para validar endpoints de la API.

---

### Phase 5: Dashboard Completo y Features Operacionales

**Rationale:** Con todos los colectores funcionando y datos reales en DB, el frontend puede construirse sobre metricas reales sin mocks. Esta fase convierte el MVP funcional en una herramienta completa para el flujo de trabajo del tecnico.
**Delivers:** Filtro por zona/sitio en dashboard, busqueda rapida de equipos/ONUs, modo mantenimiento (silencio temporal de alertas), umbrales de senal configurables por equipo (warning/critical en dBm), export CSV de incidentes.
**Addresses:** Dashboard filtrado por zona, busqueda, modo mantenimiento, umbrales configurables, export de reportes.
**Research flag:** Patrones de UI bien establecidos (shadcn/ui + Recharts). No necesita research-phase.

---

### Phase 6: Hardening y Produccion

**Rationale:** Antes de operar con 500 equipos reales sin supervision constante, los aspectos de seguridad y resiliencia deben estar completos. Esta fase convierte el sistema en uno listo para produccion.
**Delivers:** Encriptacion Fernet de credenciales de dispositivos en DB, circuit breaker definitivo por device (N fallos → skip M minutos), monitoreo del propio NOC (alerta si DB crece demasiado, si el ciclo de polling se atrasa respecto al intervalo), variables de entorno Railway auditadas, runbook operativo basico.
**Avoids:** Credenciales de 500 equipos en texto plano (C3 corolario), workers saturados por equipos irresponsivos (C3 definitivo), disco lleno silencioso (C4 monitoreo activo), filesystem efimero (C6 verificacion final).
**Research flag:** Ingenieria de hardening con patrones conocidos. No necesita research-phase.

---

### Phase Ordering Rationale

- **Infraestructura primero (Phase 0):** La conectividad de red es un bloqueante fisico, no tecnico. Si Railway no puede alcanzar los equipos, el codigo es irrelevante.
- **Pipeline base antes que metricas ricas (Phase 1 antes que 2-4):** Validar el ciclo completo scheduler → worker → DB → SSE → browser con ICMP antes de agregar complejidad de protocolo. Produce valor inmediato al tecnico.
- **Mikrotik antes que VSOL (Phase 2 antes que 3):** El colector mas simple valida el Protocol Adapter Pattern antes del mas complejo. Detectar problemas de diseno del framework con la biblioteca mejor documentada.
- **VSOL antes que Ubiquiti/Mimosa (Phase 3 antes que 4):** VSOL es el colector critico (concentra muchos clientes GPON) y el mas riesgoso. Aislar su complejidad en Phase 3 hace que Phase 4 sea mas predecible.
- **Frontend completo al final (Phase 5):** Construir el dashboard sobre datos reales evita mocks que luego no coinciden con la estructura real — el anti-patron mas comun en proyectos NOC.

---

### Research Flags

Fases que necesitan investigacion adicional o validacion contra hardware real:

- **Phase 0:** Decision de topologia de acceso de red — VPN WireGuard vs IP publica vs agente local — depende de la red especifica de BEEPYRED. Requiere reunion con el tecnico antes de comenzar.
- **Phase 3 (VSOL):** Comandos CLI exactos por modelo y firmware — requiere sesion hands-on con las OLTs reales antes de escribir los parsers. Presupuestar 2-3 dias de investigacion.
- **Phase 4 (Ubiquiti):** Confirmar si BEEPYRED tiene UISP/UNMS activo. Si si, la integracion es REST simple. Si no, requiere parseo SSH con variaciones por firmware — esfuerzo significativamente mayor.
- **Phase 4 (Mimosa):** Validar autenticacion por cookie contra los modelos especificos (B5, A5x) y firmware desplegado en produccion.

Fases con patrones bien establecidos (no necesitan research-phase):

- **Phase 1:** Celery + asyncio + PostgreSQL + JWT son patrones con documentacion abundante y ejemplos de produccion.
- **Phase 2:** RouterOS API + librouteros tiene documentacion oficial completa y alta confianza.
- **Phase 5:** Patrones de UI para dashboards NOC son bien conocidos (shadcn/ui + Recharts + TanStack Query).
- **Phase 6:** Hardening con Fernet, circuit breaker y monitoreo son patrones de ingenieria estandar.

---

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | Python + FastAPI + Celery + Redis es el stack estandar en automatizacion de redes. librouteros y asyncssh son bibliotecas activas documentadas. Railway multi-service con Docker bien documentado. |
| Features | HIGH | Modelo de features para NOC ISP bien conocido. APIs de Mikrotik (oficial), Ubiquiti UISP (swagger publico) y Mimosa (docs oficiales) documentadas. |
| Architecture | HIGH | Protocol Adapter Pattern, monolito modular con worker, SSE sobre WebSocket — patrones establecidos en LibreNMS, Zabbix, Netdata con casos de uso similares. |
| Pitfalls | HIGH (C1-C6), MEDIUM (M1-M4) | Pitfalls criticos son ampliamente documentados en comunidad de monitoreo. Pitfalls moderados requieren validacion contra versiones especificas del hardware de BEEPYRED. |
| VSOL Integration | MEDIUM | VSOL es fabricante chino con documentacion limitada en espanol/ingles. Comandos SSH varian por modelo y firmware. Requiere validacion hands-on contra el hardware real. |
| Mimosa Integration | MEDIUM | API REST documentada oficialmente pero autenticacion por cookie debe validarse contra los modelos y firmware especificos de BEEPYRED. |
| Network Connectivity | LOW-MEDIUM | Completamente dependiente de la topologia de red del ISP. Debe resolverse antes de cualquier desarrollo — no es posible evaluar sin conocer la topologia actual. |

**Overall confidence:** MEDIUM-HIGH

El stack y la arquitectura tienen alta confianza basada en patrones maduros. Las integraciones con fabricantes especificos (especialmente VSOL) tienen incertidumbre que solo se resuelve con acceso al hardware real de BEEPYRED.

### Gaps to Address

- **Topologia de red y acceso:** Antes de Phase 0, confirmar como el worker NOC alcanzara los equipos. Opciones: VPN WireGuard en Mikrotik core, IP publica con firewall restricto a IPs de Railway, o Celery worker on-premises. Esta decision afecta costo y complejidad del deployment.
- **Inventario de modelos VSOL:** Antes de Phase 3, listar exactamente los modelos de OLT VSOL en produccion (V1600D, V1600G, V1800, etc.) y sus versiones de firmware para determinar que comandos CLI usar.
- **Presencia de UISP/UNMS:** Antes de Phase 4 Ubiquiti, confirmar si existe UISP/UNMS desplegado. Cambia drasticamente el esfuerzo de integracion.
- **Version de RouterOS:** Antes de Phase 2, inventariar distribucion de versiones ROS v6 vs v7 en la red para disenar los adaptadores correctamente desde el inicio.
- **Conteo de dispositivos por tipo:** Entender cuantos Mikrotik vs OLT vs Ubiquiti vs Mimosa existen para calibrar las estimaciones de tiempo por fase.
- **Egress IPs de Railway:** Determinar si Railway publica IPs fijas de egreso para configurar reglas de firewall en los Mikrotik core. Si no, Tailscale o WireGuard son necesarios.
- **Wisphub como fuente de inventario:** Si el inventario de equipos ya existe en Wisphub, un script de importacion CSV en Phase 0/1 evita la carga manual de 500+ equipos.

---

## Sources

### Primary (HIGH confidence)
- FastAPI official docs (https://fastapi.tiangolo.com) — REST API, SSE, OAuth2, WebSocket
- librouteros PyPI (https://pypi.org/project/librouteros/) — RouterOS API client Python
- asyncssh docs (https://asyncssh.readthedocs.io) — SSH async Python
- Mikrotik RouterOS API docs (https://help.mikrotik.com/docs/display/ROS/API) — comandos y endpoints
- Ubiquiti UISP API docs (https://uisp.ui.com/api-docs) — REST API con swagger publico
- Mimosa API docs (https://docs.mimosa.co/api) — REST API oficial
- Celery docs (https://docs.celeryq.dev) — task queue, beat scheduler, gevent pool
- python-telegram-bot docs (https://python-telegram-bot.readthedocs.io) — Telegram alertas async
- Railway docs (https://docs.railway.com) — deployment, addons, filesystem efimero
- shadcn/ui (https://ui.shadcn.com) — componentes UI
- TanStack Query (https://tanstack.com/query/latest) — server state management React
- LibreNMS (https://github.com/librenms/librenms) — patrones de polling y alert deduplication
- PostgreSQL partitioning docs — PARTITION BY RANGE para time-series

### Secondary (MEDIUM confidence)
- Comunidad ISP Colombia / foros tecnicos — comandos CLI VSOL especificos por modelo y firmware
- Zabbix architecture docs — separacion scheduler/poller/trapper
- Patrones NOC/NMS de dominio consolidados (sin URL especifica verificada en este ciclo de research)

### Tertiary (LOW confidence — requieren validacion)
- Comportamiento SSH VSOL por modelo especifico — requiere validacion hands-on contra hardware real de BEEPYRED
- Autenticacion Mimosa por version de firmware — requiere validacion contra equipos especificos del ISP
- Limite exacto de sesiones concurrentes RouterOS API por version — varia segun configuracion del equipo

**Nota:** WebSearch y WebFetch no disponibles en este entorno de research. Todo basado en conocimiento de entrenamiento (cutoff agosto 2025). Validar versiones de bibliotecas al inicio del proyecto contra PyPI y npm.

---
*Research completed: 2026-04-25*
*Ready for roadmap: yes*
