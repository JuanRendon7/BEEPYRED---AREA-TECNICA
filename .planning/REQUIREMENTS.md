# BEEPYRED NOC — Requirements v1

**Project:** BEEPYRED Network Operations Center
**Scope:** v1 — Monitoreo en tiempo real, 500+ equipos, deploy en Railway
**Date:** 2026-04-25

---

## v1 Requirements

### INFRA — Infraestructura y Conectividad

- [x] **INFRA-01**: El sistema establece túnel VPN WireGuard desde Railway a la red privada del ISP para alcanzar los equipos de red
- [ ] **INFRA-02**: Base de datos PostgreSQL externo (Railway managed) configurada desde el inicio — sin almacenamiento local efímero
- [x] **INFRA-03**: Variables de entorno para todas las credenciales (ninguna credencial hardcodeada en el código)

### AUTH — Autenticación

- [ ] **AUTH-01**: El técnico puede iniciar sesión con usuario y contraseña para acceder a la plataforma
- [ ] **AUTH-02**: La sesión persiste entre visitas (JWT con expiración configurable)
- [ ] **AUTH-03**: La plataforma es inaccesible sin autenticación (rutas protegidas)

### INV — Inventario de Equipos

- [ ] **INV-01**: El técnico puede registrar un equipo con: nombre, IP, tipo (Mikrotik / OLT VSOL GPON / OLT VSOL EPON / ONU / Ubiquiti / Mimosa / Otro), sitio/ubicación, estado inicial
- [ ] **INV-02**: El técnico puede agrupar equipos por sitio geográfico (ej: Torre Norte, Nodo Centro, Repetidor Km12)
- [ ] **INV-03**: El técnico puede agregar, editar y eliminar equipos del inventario
- [ ] **INV-04**: El inventario muestra estado actual (UP/DOWN/WARNING/UNKNOWN) de cada equipo en tiempo real

### POLL — Polling y Estado

- [ ] **POLL-01**: El sistema ejecuta ICMP ping a todos los equipos del inventario cada 60 segundos
- [ ] **POLL-02**: El polling es concurrente con límite de concurrencia configurable (máx 50 simultáneos) para evitar saturar la red
- [ ] **POLL-03**: Un equipo se declara DOWN solo después de 3 polls consecutivos fallidos (debounce anti-falsos-positivos)
- [ ] **POLL-04**: El estado UP/DOWN se actualiza en el dashboard sin recargar la página (Server-Sent Events)
- [ ] **POLL-05**: Los equipos que no responden en N segundos tienen timeout individual y no bloquean el ciclo de polling

### MK — Mikrotik RouterOS API

- [ ] **MK-01**: El sistema recolecta CPU actual (%) y RAM usada (%) de cada router Mikrotik vía RouterOS API
- [ ] **MK-02**: El sistema recolecta tráfico TX/RX (bps) por interfaz en cada router Mikrotik vía RouterOS API
- [ ] **MK-03**: Las sesiones RouterOS API se cierran correctamente después de cada consulta (sin sesiones zombie)
- [ ] **MK-04**: El collector Mikrotik tiene circuit breaker: después de 3 fallos consecutivos suspende polling por 5 minutos antes de reintentar

### VSOL — OLTs VSOL y ONUs

- [ ] **VSOL-01**: El sistema se conecta por SSH a las OLTs VSOL GPON (8 puertos) y recolecta: lista de ONUs por puerto PON, señal óptica Rx/Tx (dBm), estado (ONLINE/OFFLINE/RANGING)
- [ ] **VSOL-02**: El sistema se conecta por SSH a las OLTs VSOL EPON (4 puertos) y recolecta: lista de ONUs por puerto, señal Rx/Tx (dBm), estado
- [ ] **VSOL-03**: Las conexiones SSH a OLTs VSOL tienen timeout duro (30s) y se cierran correctamente después de cada consulta
- [ ] **VSOL-04**: El collector VSOL tiene circuit breaker por OLT: suspende polling de esa OLT tras 3 fallos consecutivos sin afectar el resto del sistema
- [ ] **VSOL-05**: Cada ONU aparece en el inventario con su OLT padre y puerto PON asociado

### UBI — Ubiquiti (vía UISP API)

- [ ] **UBI-01**: El sistema recolecta señal (dBm), CCQ (%) y throughput TX/RX (Mbps) de los radioenlaces Ubiquiti vía UISP REST API
- [ ] **UBI-02**: La autenticación con UISP usa API key configurable por variable de entorno
- [ ] **UBI-03**: El collector Ubiquiti/UISP maneja errores de red y expiración de sesión sin detener el ciclo de polling general

### MIM — Mimosa

- [ ] **MIM-01**: El sistema recolecta RSSI (dBm), modulación MCS y throughput TX/RX (Mbps) de cada equipo Mimosa vía API REST local del equipo
- [ ] **MIM-02**: La autenticación con Mimosa API renueva la sesión/cookie automáticamente cuando expira
- [ ] **MIM-03**: El collector Mimosa tiene circuit breaker por equipo tras fallos consecutivos

### ALERT — Alertas y Notificaciones

- [ ] **ALERT-01**: El sistema envía mensaje a Telegram cuando un equipo pasa a estado DOWN (después del debounce de 3 polls)
- [ ] **ALERT-02**: El sistema envía mensaje a Telegram cuando un equipo se recupera (DOWN → UP), indicando duración de la caída
- [ ] **ALERT-03**: El sistema envía alerta a Telegram cuando la señal óptica de una ONU GPON cae por debajo de -28 dBm
- [ ] **ALERT-04**: El sistema envía alerta a Telegram cuando el CPU de un router Mikrotik supera el 90% por más de 2 minutos consecutivos
- [ ] **ALERT-05**: Los umbrales de alerta (dBm, CPU %) son configurables sin tocar el código
- [ ] **ALERT-06**: Los mensajes de Telegram incluyen: nombre del equipo, IP, sitio/ubicación, tipo de problema, timestamp

### DASH — Dashboard y Visualización

- [ ] **DASH-01**: La pantalla principal muestra todos los equipos con estado UP/DOWN/WARNING actualizado en tiempo real
- [ ] **DASH-02**: El técnico puede filtrar la vista por: tipo de equipo, sitio/ubicación, estado (UP/DOWN/WARNING)
- [ ] **DASH-03**: Al hacer clic en un equipo se muestra tarjeta de detalle con métricas actuales (CPU, RAM, señal, tráfico según tipo)
- [ ] **DASH-04**: El dashboard tiene indicador de resumen: total equipos, cuántos UP, cuántos DOWN, cuántos WARNING
- [ ] **DASH-05**: Las métricas clave muestran gráfica de tendencia de las últimas 24 horas en la tarjeta de detalle

### INC — Historial e Incidentes

- [ ] **INC-01**: El sistema registra automáticamente cada incidente: equipo afectado, hora de inicio (DOWN), hora de recuperación (UP), duración total
- [ ] **INC-02**: El técnico puede ver la lista de incidentes ordenada por fecha, filtrable por equipo y sitio
- [ ] **INC-03**: Las métricas históricas se retienen 30 días; los incidentes se retienen 30 días
- [ ] **INC-04**: La base de datos tiene política de limpieza automática para no crecer indefinidamente

### DEPLOY — Deploy y Operaciones

- [x] **DEPLOY-01**: La aplicación corre en Railway con dos servicios: web (FastAPI) y worker (Celery)
- [x] **DEPLOY-02**: El dominio personalizado de BEEPYRED apunta a la instancia en Railway
- [ ] **DEPLOY-03**: Las credenciales de equipos (usuario/contraseña SSH, API keys) están encriptadas en base de datos, no en texto plano

---

## v2 — Diferido

- **Control remoto de equipos**: reiniciar, cambiar configuración vía API — v2 una vez estabilizado el monitoreo
- **Correlación de fallas en cascada**: si cae un router upstream, suprimir alertas de sus ONUs dependientes — requiere topología
- **Vista topológica / mapa de red**: grafo de dependencias entre equipos — diferido por complejidad
- **Integración con Wisphub**: mapeo ONU → cliente de Wisphub — explorar cuando el NOC esté estable
- **Multi-usuario con roles**: técnicos junior, gerencia, solo lectura — v2; v1 es para el técnico principal
- **BGP/OSPF monitoring**: estado de sesiones de routing — v2
- **App móvil nativa**: Railway + web responsive es suficiente para v1

---

## Out of Scope

- Facturación, gestión de clientes, CRM — Wisphub lo maneja; esta plataforma es solo técnica
- Gestión de tickets de soporte — herramienta separada
- Monitoreo de servicios de terceros (upstream, tránsitos) — fuera del alcance del ISP privado
- Aprovisionamiento automático de ONUs — riesgo demasiado alto sin validación humana

---

## Traceability

| REQ-ID | Phase | Status |
|--------|-------|--------|
| INFRA-01 | Phase 1: Infrastructure | Complete |
| INFRA-02 | Phase 1: Infrastructure | Pending |
| INFRA-03 | Phase 1: Infrastructure | Complete |
| DEPLOY-01 | Phase 1: Infrastructure | Complete |
| DEPLOY-02 | Phase 6: Dashboard Completo | Complete |
| DEPLOY-03 | Phase 1: Infrastructure | Pending |
| AUTH-01 | Phase 2: Foundation | Pending |
| AUTH-02 | Phase 2: Foundation | Pending |
| AUTH-03 | Phase 2: Foundation | Pending |
| INV-01 | Phase 2: Foundation | Pending |
| INV-02 | Phase 2: Foundation | Pending |
| INV-03 | Phase 2: Foundation | Pending |
| INV-04 | Phase 2: Foundation | Pending |
| POLL-01 | Phase 2: Foundation | Pending |
| POLL-02 | Phase 2: Foundation | Pending |
| POLL-03 | Phase 2: Foundation | Pending |
| POLL-04 | Phase 2: Foundation | Pending |
| POLL-05 | Phase 2: Foundation | Pending |
| MK-01 | Phase 3: Mikrotik + Alertas + Incidentes | Pending |
| MK-02 | Phase 3: Mikrotik + Alertas + Incidentes | Pending |
| MK-03 | Phase 3: Mikrotik + Alertas + Incidentes | Pending |
| MK-04 | Phase 3: Mikrotik + Alertas + Incidentes | Pending |
| ALERT-01 | Phase 3: Mikrotik + Alertas + Incidentes | Pending |
| ALERT-02 | Phase 3: Mikrotik + Alertas + Incidentes | Pending |
| ALERT-03 | Phase 3: Mikrotik + Alertas + Incidentes | Pending |
| ALERT-04 | Phase 3: Mikrotik + Alertas + Incidentes | Pending |
| ALERT-05 | Phase 3: Mikrotik + Alertas + Incidentes | Pending |
| ALERT-06 | Phase 3: Mikrotik + Alertas + Incidentes | Pending |
| INC-01 | Phase 3: Mikrotik + Alertas + Incidentes | Pending |
| INC-02 | Phase 3: Mikrotik + Alertas + Incidentes | Pending |
| INC-03 | Phase 3: Mikrotik + Alertas + Incidentes | Pending |
| INC-04 | Phase 3: Mikrotik + Alertas + Incidentes | Pending |
| VSOL-01 | Phase 4: VSOL OLT Collector | Pending |
| VSOL-02 | Phase 4: VSOL OLT Collector | Pending |
| VSOL-03 | Phase 4: VSOL OLT Collector | Pending |
| VSOL-04 | Phase 4: VSOL OLT Collector | Pending |
| VSOL-05 | Phase 4: VSOL OLT Collector | Pending |
| UBI-01 | Phase 5: Ubiquiti y Mimosa Collectors | Pending |
| UBI-02 | Phase 5: Ubiquiti y Mimosa Collectors | Pending |
| UBI-03 | Phase 5: Ubiquiti y Mimosa Collectors | Pending |
| MIM-01 | Phase 5: Ubiquiti y Mimosa Collectors | Pending |
| MIM-02 | Phase 5: Ubiquiti y Mimosa Collectors | Pending |
| MIM-03 | Phase 5: Ubiquiti y Mimosa Collectors | Pending |
| DASH-01 | Phase 6: Dashboard Completo | Pending |
| DASH-02 | Phase 6: Dashboard Completo | Pending |
| DASH-03 | Phase 6: Dashboard Completo | Pending |
| DASH-04 | Phase 6: Dashboard Completo | Pending |
| DASH-05 | Phase 6: Dashboard Completo | Pending |
