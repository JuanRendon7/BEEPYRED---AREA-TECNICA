# BEEPYRED NOC — Network Operations Center

## What This Is

Plataforma web de monitoreo de red en tiempo real para BEEPYRED ISP GROUP SAS, proveedor de internet en San Luis, Antioquia. Consolida en un solo dashboard el estado de todos los equipos de la red: Mikrotik, OLTs VSOL, ONUs GPON, radioenlaces Ubiquiti y Mimosa. Diseñada para uso del técnico de red con alertas inmediatas vía Telegram e historial de incidentes.

## Core Value

El técnico debe poder ver en un solo vistazo qué equipo está caído o degradado, sin tener que entrar a cada equipo individualmente.

## Requirements

### Validated

(None yet — ship to validate)

### Active

- [ ] Dashboard unificado con estado de todos los equipos en tiempo real
- [ ] Integración con Mikrotik RouterOS API para métricas (CPU, RAM, interfaces, tráfico)
- [ ] Integración con OLTs VSOL vía SSH/Telnet para estado de ONUs y puertos PON
- [ ] Integración con radioenlaces Ubiquiti (UISP API / AirOS SSH) para señal y throughput
- [ ] Integración con radioenlaces Mimosa (API REST) para señal y throughput
- [ ] Alertas por Telegram cuando un equipo se cae o supera umbrales configurados
- [ ] Historial de incidentes: qué falló, a qué hora, cuánto duró la caída
- [ ] Inventario de equipos (nombre, IP, tipo, ubicación, estado)
- [ ] Indicadores por equipo: estado UP/DOWN, latencia, carga de CPU/RAM, tráfico
- [ ] Estado de ONUs GPON: señal óptica (Rx/Tx dBm), estado, cliente asociado
- [ ] Mapa o vista topológica de la red (deseable)
- [ ] Autenticación básica para acceso a la plataforma

### Out of Scope

- Facturación y gestión de clientes — Wisphub lo cubre; esta plataforma es solo monitoreo técnico
- Control remoto de equipos (reinicios, cambios de config) — v2; primero monitorear
- App móvil nativa — Railway + responsive web es suficiente para v1
- Integración profunda con Wisphub — explorar en v2 una vez estabilizado el monitoreo

## Context

- **ISP:** BEEPYRED ISP GROUP SAS, San Luis, Antioquia, Colombia
- **Red:** Más de 500 equipos activos en producción
- **Equipos principales:**
  - Mikrotik (routers/switches) — acceso vía RouterOS API y SSH
  - OLT VSOL (GPON) — acceso vía SSH/Telnet; algunos modelos con SNMP
  - ONUs GPON — gestionadas desde la OLT VSOL
  - Radioenlaces Ubiquiti (AirMax, AirFiber) — UISP API o SSH directo
  - Radioenlaces Mimosa (B5, A5x, etc.) — API REST
- **Gestión actual:** Wisphub para CRM/facturación; sin NOC dedicado
- **Acceso disponible:** Acceso directo a equipos principales y credenciales Wisphub
- **Destino final:** Railway con dominio propio

## Constraints

- **Conectividad:** Los equipos están en red privada — el servidor NOC debe poder alcanzarlos (VPN o IP pública en equipos core)
- **Protocolo principal:** Mikrotik API + SSH/Telnet para VSOL; evitar SNMP donde haya mejor alternativa nativa
- **Deploy:** Railway (Node.js/Python compatible) con dominio personalizado
- **Usuario único v1:** Un solo técnico; sin necesidad de roles complejos en v1
- **Tiempo real:** Polling cada 30-60 segundos es suficiente; no se requiere streaming sub-segundo

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| SSH/API nativa sobre SNMP | RouterOS API y SSH dan más datos con mejor estructura que SNMP para estos equipos | — Pending |
| Telegram sobre WhatsApp para alertas | Telegram tiene API oficial gratuita y robusta; WhatsApp Business API tiene costo y complejidad | — Pending |
| Railway para deploy | Plataforma PaaS simple, soporte Docker, dominio propio, sin administrar servidores | — Pending |
| Wisphub separado en v1 | Evita complejidad de integración mientras se valida el monitoreo core | — Pending |

## Evolution

Este documento evoluciona en cada transición de fase y milestone.

**Después de cada fase** (via `/gsd-transition`):
1. ¿Requisitos invalidados? → Mover a Out of Scope con razón
2. ¿Requisitos validados? → Mover a Validated con referencia de fase
3. ¿Nuevos requisitos? → Agregar a Active
4. ¿Decisiones a registrar? → Agregar a Key Decisions
5. ¿"What This Is" sigue siendo exacto? → Actualizar si hay drift

**Después de cada milestone** (via `/gsd-complete-milestone`):
1. Revisión completa de todas las secciones
2. Verificar Core Value — ¿sigue siendo la prioridad correcta?
3. Auditar Out of Scope — ¿las razones siguen siendo válidas?
4. Actualizar Context con estado actual

---
*Last updated: 2026-04-25 after initialization*
