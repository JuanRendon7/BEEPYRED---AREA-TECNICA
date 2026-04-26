# Roadmap: BEEPYRED NOC

## Overview

El proyecto construye de adentro hacia afuera: primero la infraestructura que conecta Railway a la red privada del ISP, luego el pipeline de polling con ICMP para validar el ciclo completo, luego los collectors por fabricante (Mikrotik primero por ser el mejor documentado, VSOL aislado por ser el mas complejo, Ubiquiti y Mimosa despues), y finalmente el dashboard completo sobre datos reales. Cada fase entrega valor verificable antes de comenzar la siguiente. El tecnico ve datos reales en pantalla desde Phase 2 y recibe alertas desde Phase 3.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [ ] **Phase 1: Infrastructure** - VPN, PostgreSQL schema, Railway multi-service, variables de entorno
- [ ] **Phase 2: Foundation** - Auth, inventario de equipos, polling ICMP, SSE dashboard basico
- [ ] **Phase 3: Mikrotik + Alertas + Incidentes** - RouterOS API collector, motor de alertas Telegram con debounce, historial de incidentes
- [ ] **Phase 4: VSOL OLT Collector** - SSH/CLI parsing para OLTs VSOL GPON y EPON, estado y señal de ONUs
- [ ] **Phase 5: Ubiquiti y Mimosa Collectors** - UISP REST API y Mimosa REST API, metricas de radioenlaces
- [ ] **Phase 6: Dashboard Completo** - Filtros, detalle por equipo, graficas de tendencia 24h, deploy final con dominio propio

## Phase Details

### Phase 1: Infrastructure
**Goal**: El entorno de ejecucion del NOC esta listo: Railway conecta a la red privada del ISP, PostgreSQL persiste todos los datos, y ninguna credencial existe en el codigo
**Depends on**: Nothing (first phase)
**Requirements**: INFRA-01, INFRA-02, INFRA-03, DEPLOY-01, DEPLOY-02, DEPLOY-03
**Success Criteria** (what must be TRUE):
  1. El worker en Railway puede hacer ping a un equipo de la red privada del ISP (valida el tunel VPN — Tailscale userspace en lugar de WireGuard kernel, que es imposible en Railway)
  2. La base de datos PostgreSQL externa existe con el schema inicial (devices, device_credentials, metrics, alerts, incidents, onus) y no usa almacenamiento local efimero
  3. Los servicios web, worker y beat se despliegan en Railway desde el mismo Dockerfile sin errores
  4. Todas las credenciales (DB, Redis, VPN, Telegram) son variables de entorno — ninguna esta hardcodeada en el codigo ni en el repositorio
  5. Las credenciales de equipos de red almacenadas en DB estan encriptadas con Fernet, no en texto plano
**Plans**: 2 plans

Plans:
- [x] 01-01-PLAN.md — Scaffold del monorepo, Dockerfile multi-stage (Tailscale worker), pydantic-settings config, railway.toml
- [x] 01-02-PLAN.md — Modelos SQLAlchemy, Alembic async setup, migracion inicial, Fernet security, tests unitarios

### Phase 2: Foundation
**Goal**: El tecnico puede iniciar sesion, registrar equipos en el inventario, y ver en tiempo real cuales estan UP y cuales DOWN — sin necesidad de metricas ricas, solo ICMP ping
**Depends on**: Phase 1
**Requirements**: AUTH-01, AUTH-02, AUTH-03, INV-01, INV-02, INV-03, INV-04, POLL-01, POLL-02, POLL-03, POLL-04, POLL-05
**Success Criteria** (what must be TRUE):
  1. El tecnico puede iniciar sesion con usuario y contrasena y la sesion persiste entre visitas (JWT); sin autenticacion la plataforma es inaccesible
  2. El tecnico puede agregar, editar y eliminar equipos en el inventario con nombre, IP, tipo y sitio, y agruparlos por sitio geografico
  3. El sistema ejecuta ICMP ping a todos los equipos del inventario cada 60 segundos con concurrencia limitada a 50 simultaneos y timeout individual por equipo
  4. Un equipo aparece como DOWN en pantalla solo despues de 3 polls consecutivos fallidos (no en el primer timeout)
  5. El estado UP/DOWN de cada equipo se actualiza en el dashboard sin recargar la pagina (Server-Sent Events)
**Plans**: 4 plans

Plans:
- [ ] 02-01-PLAN.md — Auth backend: PyJWT + pwdlib/Argon2, modelo User, migracion 002, seed_admin, tests AUTH-01/02/03
- [ ] 02-02-PLAN.md — Inventario backend: schemas Pydantic, CRUD /devices con filtro por sitio, tests INV-01/02/03/04
- [ ] 02-03-PLAN.md — ICMP polling worker: ping_host + asyncio.Semaphore + consecutive_failures + Redis pub/sub, Celery beat 60s
- [ ] 02-04-PLAN.md — SSE endpoint /events + frontend React (Vite + shadcn/ui + login + dashboard + inventory CRUD)

### Phase 3: Mikrotik + Alertas + Incidentes
**Goal**: El tecnico recibe alertas en Telegram cuando un equipo cae o se recupera, ve metricas CPU/RAM/trafico de los Mikrotik, y puede consultar el historial de incidentes
**Depends on**: Phase 2
**Requirements**: MK-01, MK-02, MK-03, MK-04, ALERT-01, ALERT-02, ALERT-03, ALERT-04, ALERT-05, ALERT-06, INC-01, INC-02, INC-03, INC-04
**Success Criteria** (what must be TRUE):
  1. El dashboard muestra CPU (%), RAM (%) y trafico TX/RX (bps) por interfaz de cada router Mikrotik, recolectados via RouterOS API
  2. El tecnico recibe un mensaje Telegram cuando un equipo pasa a DOWN (tras 3 fallos) con nombre, IP, sitio y timestamp; recibe otro cuando se recupera con duracion de la caida
  3. El sistema registra automaticamente cada incidente (equipo, hora inicio, hora fin, duracion) y el tecnico puede ver la lista filtrada por equipo y sitio
  4. Las metricas historicas y los incidentes se retienen 30 dias con limpieza automatica que previene crecimiento indefinido de la DB
  5. Los umbrales de alerta (CPU %, dBm ONU) son configurables sin tocar el codigo; el collector Mikrotik tiene circuit breaker que suspende polling 5 minutos tras 3 fallos consecutivos
**Plans**: TBD

### Phase 4: VSOL OLT Collector
**Goal**: El tecnico puede ver el estado de todas las ONUs GPON y EPON — online/offline y senal optica Rx/Tx dBm — recolectado via SSH a las OLTs VSOL
**Depends on**: Phase 3
**Requirements**: VSOL-01, VSOL-02, VSOL-03, VSOL-04, VSOL-05
**Success Criteria** (what must be TRUE):
  1. El sistema se conecta por SSH a las OLTs VSOL GPON (8 puertos) y EPON (4 puertos) y muestra la lista de ONUs por puerto con estado ONLINE/OFFLINE/RANGING y senal Rx/Tx dBm
  2. Cada ONU aparece en el inventario con su OLT padre y puerto PON asociado
  3. Las conexiones SSH tienen timeout duro de 30 segundos y se cierran correctamente — no quedan conexiones colgadas en la OLT
  4. Si una OLT falla 3 veces consecutivas su polling se suspende sin afectar el polling del resto de equipos (circuit breaker por OLT)
  5. El tecnico recibe alerta Telegram cuando la senal optica de una ONU GPON cae por debajo del umbral configurado (-28 dBm por defecto)
**Plans**: TBD

### Phase 5: Ubiquiti y Mimosa Collectors
**Goal**: El tecnico puede ver el estado de los radioenlaces Ubiquiti y Mimosa — senal, CCQ/modulacion y throughput — directamente en el dashboard
**Depends on**: Phase 4
**Requirements**: UBI-01, UBI-02, UBI-03, MIM-01, MIM-02, MIM-03
**Success Criteria** (what must be TRUE):
  1. El dashboard muestra senal (dBm), CCQ (%) y throughput TX/RX (Mbps) de los radioenlaces Ubiquiti, recolectados via UISP REST API con autenticacion por API key configurable
  2. El dashboard muestra RSSI (dBm), modulacion MCS y throughput TX/RX (Mbps) de los equipos Mimosa, recolectados via API REST local
  3. El collector Mimosa renueva automaticamente la sesion cuando expira sin detener el ciclo de polling
  4. Errores de red o de sesion en Ubiquiti o Mimosa no detienen el ciclo de polling de los demas equipos
**Plans**: TBD

### Phase 6: Dashboard Completo
**Goal**: El dashboard es la herramienta operacional completa: el tecnico puede filtrar por tipo y sitio, ver el detalle de cualquier equipo con graficas de tendencia 24h, y el dominio propio de BEEPYRED esta activo
**Depends on**: Phase 5
**Requirements**: DASH-01, DASH-02, DASH-03, DASH-04, DASH-05
**Success Criteria** (what must be TRUE):
  1. La pantalla principal muestra todos los equipos con estado UP/DOWN/WARNING en tiempo real y un resumen del totales (UP, DOWN, WARNING)
  2. El tecnico puede filtrar la vista por tipo de equipo, sitio/ubicacion y estado; la lista se actualiza sin recargar la pagina
  3. Al hacer clic en un equipo se abre tarjeta de detalle con las metricas actuales (CPU, RAM, senal, trafico segun tipo de equipo)
  4. La tarjeta de detalle muestra grafica de tendencia de las ultimas 24 horas para las metricas clave del equipo
  5. El dominio personalizado de BEEPYRED apunta a la instancia en Railway y el acceso HTTPS funciona correctamente
**Plans**: TBD
**UI hint**: yes

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4 → 5 → 6

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Infrastructure | 2/2 | Complete | 2026-04-26 |
| 2. Foundation | 0/4 | Planned | - |
| 3. Mikrotik + Alertas + Incidentes | 0/TBD | Not started | - |
| 4. VSOL OLT Collector | 0/TBD | Not started | - |
| 5. Ubiquiti y Mimosa Collectors | 0/TBD | Not started | - |
| 6. Dashboard Completo | 0/TBD | Not started | - |
