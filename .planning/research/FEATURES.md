# Feature Landscape — BEEPYRED NOC

**Domain:** Network Operations Center (NOC) para ISP mediano — 500+ equipos mixtos
**Researched:** 2026-04-25
**Confidence:** MEDIUM-HIGH (basado en conocimiento consolidado de RouterOS API, VSOL OLT, UISP/AirOS, Mimosa API; sin acceso a web en este entorno)

---

## Contexto del Dominio

Un NOC para ISP mediano con equipos heterogeneos (Mikrotik, OLT GPON, Ubiquiti, Mimosa) enfrenta
el problema de visibilidad fragmentada: cada fabricante tiene su propia interfaz, protocolo y
jerarquía de datos. El valor central no es monitorear en silado — es correlacionar fallas en capas
(fibra óptica → ONU → backbone Mikrotik → radioenlace Ubiquiti/Mimosa → cliente final).

---

## Table Stakes

Features que el técnico da por sentado. Ausencia = plataforma inutilizable o abandonada.

| Feature | Por Qué Es Imprescindible | Complejidad | Notas de Implementación |
|---------|--------------------------|-------------|------------------------|
| Dashboard unificado UP/DOWN | Sin esto el técnico sigue revisando equipos uno a uno | Baja | Estado binario por equipo con timestamp del último check |
| Polling periódico configurable | Base de todo el monitoreo; sin datos, no hay NOC | Media | 30-60 s para v1; intervalo por tipo de equipo |
| Inventario de equipos | El técnico necesita saber qué existe antes de monitorear | Baja | Nombre, IP, tipo (Mikrotik/OLT/Ubiquiti/Mimosa), sitio/ubicación, estado |
| Estado UP/DOWN por equipo | Pregunta básica: "¿está encendido?" | Baja | ICMP ping como fallback universal; API nativa como fuente primaria |
| Latencia (RTT) por equipo | Distingue "caído" de "lento" | Baja | Ping con timestamp; percentil p95 en ventana de 5 min |
| Alertas Telegram al bajar | El técnico no vive pegado al dashboard | Media | Bot Telegram con mensaje estructurado: equipo + sitio + duración + tipo de falla |
| Alertas Telegram al recuperar | Sin esto, el técnico no sabe cuándo terminó el problema | Baja | Mensaje de recovery con duración total del incidente |
| Historial de incidentes | Permite postmortems y reportes a supervisión | Media | Tabla: equipo, inicio, fin, duración, tipo de alerta; exportable a CSV |
| Autenticación básica | Sin login, cualquiera con la URL accede a la red interna | Baja | Usuario/contraseña hasheada; JWT session; v1 single user |
| Indicadores Mikrotik — CPU/RAM | Los Mikrotik se saturan; el técnico debe verlo antes de que fallen | Media | RouterOS API: `/system/resource` — CPU load, free memory, uptime |
| Indicadores Mikrotik — Tráfico por interfaz | Saber qué interfaz está saturada | Media | RouterOS API: `/interface` — rx-bits-per-second, tx-bits-per-second |
| Estado ONUs GPON — Rx dBm | Señal óptica es el diagnóstico fundamental en GPON; sin esto la OLT es una caja negra | Alta | SSH a OLT VSOL: comando `show pon power attenuation` o equivalente por modelo |
| Estado ONUs GPON — Online/Offline | Saber cuántas ONUs están activas en cada puerto PON | Media | SSH a OLT VSOL: `show gpon onu state` por interface gpon |
| Ubiquiti — Signal Level (dBm) | RF signal es el indicador primario de calidad de enlace AirMax/AirFiber | Media | UISP API REST o SSH AirOS: `wstalist` → signal field |
| Ubiquiti — CCQ (Client Connection Quality) | Métrica combinada de calidad; CCQ < 80% es señal de problema | Baja | UISP API o AirOS SSH: campo `ccq` en `wstalist` |
| Mimosa — RSSI (dBm) | Equivalente al signal level de Ubiquiti en enlaces Mimosa | Media | Mimosa API REST: endpoint de status del enlace → rssi |
| Mimosa — TX/RX throughput | Validar que el enlace está pasando tráfico real | Media | Mimosa API REST: stats endpoint → throughput |
| Página de detalle por equipo | El dashboard muestra estado; la página de detalle muestra métricas completas | Media | Vista individual con histórico de 24h, alertas activas, datos crudos del último poll |
| Gráficas de tendencia (últimas 24h) | Permite ver si el problema es puntual o sistémico | Media | TimeSeries en BD; gráfica básica Chart.js/Recharts para CPU, tráfico, señal |

---

## Diferenciadores

Features que no son esperados por defecto pero generan ventaja competitiva real o mejoran
significativamente la eficiencia operativa.

| Feature | Propuesta de Valor | Complejidad | Notas |
|---------|-------------------|-------------|-------|
| Correlación de fallas en cascada | Si cae un router Mikrotik upstream, todas las ONUs y radioenlaces downstream aparecen en rojo — el NOC muestra la causa raíz, no 50 alertas independientes | Alta | Requiere topología de dependencias; suprimir alertas de "hijos" cuando cae el "padre" |
| Mapa topológico interactivo | Visualización geográfica o lógica de la red; click en nodo → detalle | Alta | Leaflet.js para mapa con coordenadas GPS por equipo; o D3.js para topología lógica |
| Vista OLT → puertos PON → ONUs jerárquica | Mostrar la OLT con sus 16 puertos y las N ONUs por puerto; señal Rx por cada ONU con color semáforo | Alta | Requiere parseo estructurado de SSH output VSOL; mapeo OLT-puerto-ONU en BD |
| Umbral de señal configurable por equipo | Definir warning/critical por dBm para señal óptica y RF; diferente por tipo de enlace | Media | Tabla de thresholds en BD; alerta cuando el valor cruza el umbral, no solo cuando cae |
| Silencio temporal de alertas (maintenance mode) | Al hacer mantenimiento, suprimir alertas del equipo sin apagar el monitoreo | Baja | Flag `silenced_until` en BD; UI toggle con duración |
| Dashboard filtrado por sitio/zona | ISP con múltiples zonas geográficas; ver solo "Zona Norte" | Baja | Tag de zona en inventario + filtro en dashboard; bajo esfuerzo, alto valor operativo |
| Histórico de métricas de señal óptica (Rx dBm) | Ver si la señal de una ONU se ha degradado gradualmente (fusión sucia, conector oxidado) | Alta | Requiere almacenamiento de series de tiempo; gráfica Rx dBm últimos 7-30 días |
| Resumen de estado Mikrotik BGP/OSPF | Ver si las sesiones BGP están establecidas y el estado de los vecinos OSPF | Alta | RouterOS API: `/routing/bgp/peer` status; `/routing/ospf/neighbor` state — datos ricos pero requieren mapeo conceptual correcto |
| Tiempo de downtime acumulado (SLA view) | % disponibilidad por equipo en el último mes; base para reportes de SLA | Media | Calculado desde historial de incidentes; no requiere datos adicionales, solo cálculo |
| Notificación de degradación antes de caída | Alertar cuando señal dBm cae 3 dB respecto al baseline, antes de que la ONU se desconecte | Alta | Requiere baseline histórico + lógica de tendencia; evita fallas reactivas |
| Búsqueda rápida de cliente/equipo | Técnico escribe MAC o nombre de ONU y encuentra el equipo inmediatamente | Baja | Búsqueda full-text en inventario; campo de búsqueda en header del dashboard |
| Export CSV de incidentes | Para reportes a gerencia o auditorías | Baja | Query a BD de incidentes → descarga CSV; trivial una vez que el historial existe |

---

## Anti-Features

Features que deliberadamente NO se construyen en v1, con justificación explícita.

| Anti-Feature | Por Qué NO en v1 | Qué Hacer en Su Lugar |
|--------------|-----------------|----------------------|
| Control remoto de equipos (reboot, cambio de config) | Aumenta el radio de falla del NOC exponencialmente; un bug puede reiniciar equipos en producción | Monitoreo de solo lectura; v2 con confirmación explícita y log de auditoría |
| Gestión de tickets / help desk integrado | Complejidad de UX innecesaria; el técnico ya tiene flujos para tickets | Historial de incidentes simple con timestamps; integrar ticketing en v2 si se valida |
| Roles y permisos multi-usuario | v1 es single-user (un técnico); roles agregan complejidad sin beneficio inmediato | Un único usuario admin; agregar roles en v2 cuando haya más usuarios |
| Integración Wisphub (CRM/clientes) | Requiere mapear cliente↔equipo↔ONU; complejidad de integración alta para v1 | Inventario propio en el NOC; cruzar con Wisphub manualmente en v1 |
| App móvil nativa (iOS/Android) | Costo y tiempo de desarrollo desproporcionado; Railway + responsive web cubre el caso | Web responsive bien diseñada; alertas Telegram son el "push notification" del técnico |
| Monitoreo SNMP masivo | Para equipos con API nativa mejor (Mikrotik RouterOS API, UISP API, Mimosa REST API) SNMP es inferior en datos y más complejo de parsear | Usar API nativas; SNMP solo como fallback para equipos legacy sin API |
| Streaming sub-segundo (WebSocket push continuo) | Polling 30-60s es suficiente para este caso de uso; streaming agrega complejidad de infraestructura | Polling con actualización de UI periódica; WebSocket solo para alertas críticas si se valida |
| Provisionamiento de ONUs desde el NOC | Cambios en la OLT en producción son de alto riesgo | Solo lectura de estado; provisioning sigue en la OLT directamente |
| Dashboard ejecutivo con KPIs de negocio | El NOC es herramienta técnica, no gerencial; KPIs de negocio viven en Wisphub | Datos técnicos solamente; disponibilidad % puede exportarse como dato para uso externo |
| Autodescubrimiento de red (network scan) | Agregar equipos no conocidos al inventario automáticamente es riesgoso en una red de producción | Inventario manual o importación CSV; evitar scan de red no controlado |

---

## Inventario de Features por Tipo de Equipo

### Mikrotik RouterOS

Acceso vía **RouterOS API** (puerto 8728/8729 TLS) — preferido sobre SSH por estructura de datos.
SSH disponible como fallback.

| Metric | RouterOS API Endpoint | Confidence | Complejidad |
|--------|----------------------|------------|-------------|
| CPU load (%) | `/system/resource` → `cpu-load` | HIGH | Baja |
| Free memory (MB) | `/system/resource` → `free-memory`, `total-memory` | HIGH | Baja |
| Uptime | `/system/resource` → `uptime` | HIGH | Baja |
| Interfaces list | `/interface` → name, type, running, disabled | HIGH | Baja |
| Interface traffic (bps) | `/interface` → `rx-bits-per-second`, `tx-bits-per-second` | HIGH | Baja |
| Interface errors | `/interface` → `rx-error`, `tx-error`, `rx-drop`, `tx-drop` | HIGH | Media |
| IP addresses | `/ip/address` → address, interface, network | HIGH | Baja |
| ARP table | `/ip/arp` → address, mac-address, interface | HIGH | Baja |
| OSPF neighbors state | `/routing/ospf/neighbor` → address, state, state-changes | HIGH | Alta |
| BGP peer status | `/routing/bgp/peer` → name, remote-address, state, prefix-count | HIGH | Alta |
| BGP advertised routes | `/routing/bgp/peer/print` con detail | HIGH | Alta |
| Firewall connection tracking count | `/ip/firewall/connection/print count-only` | MEDIUM | Media |
| Active users / sessions | `/user/active` | HIGH | Baja |
| System logs (últimos N) | `/log` → time, topics, message | HIGH | Media |
| Wireless interfaces (si aplica) | `/interface/wireless` → signal-strength, noise-floor, tx-rate | HIGH | Media |
| CAPsMAN APs conectados | `/caps-man/registration-table` | MEDIUM | Alta |
| Temperatura (RouterBOARD) | `/system/health` → temperature | MEDIUM | Baja |
| Queue drops (HTB/PCQ) | `/queue/simple` o `/queue/tree` → packets-dropped | HIGH | Media |

**Datos de enrutamiento (BGP/OSPF) — notas de implementación:**
- BGP: mostrar estado de cada peer (Established/Active/Idle), ASN remoto, prefijos recibidos/anunciados
- OSPF: mostrar vecinos activos, estado de adjacency (Full/2-Way/Init), área
- Estos son features diferenciadores, no table stakes para v1
- Complejidad alta: requiere entender el modelo de datos de RouterOS y mapear correctamente

---

### OLT VSOL GPON

Acceso vía **SSH/Telnet** — la OLT VSOL no tiene API REST nativa documentada públicamente.
Algunos modelos tienen SNMP básico. El protocolo principal es CLI por SSH.

**Confidence: MEDIUM** — VSOL es fabricante chino con documentación limitada en inglés/español;
los comandos varían por firmware version y modelo (V1600, V1600G2, V1600D, V1800, etc.).

| Metric | Comando SSH (aproximado por modelo) | Confidence | Complejidad |
|--------|-------------------------------------|------------|-------------|
| ONUs en línea por puerto | `show gpon onu state gpon-onu_X/X` | MEDIUM | Alta |
| Señal Rx ONU (dBm) | `show pon power attenuation gpon-onu_X/X:X` | MEDIUM | Alta |
| Señal Tx OLT hacia ONU (dBm) | incluido en el mismo comando de atenuación | MEDIUM | Alta |
| Estado ONU (Online/Offline/Ranging) | `show gpon onu state` | MEDIUM | Alta |
| ONU description/alias | `show gpon onu detail-info gpon-onu_X/X:X` | MEDIUM | Alta |
| MAC address de ONU | incluido en detail-info | MEDIUM | Alta |
| Serial number de ONU | `show gpon onu info gpon-onu_X/X` → SN | MEDIUM | Alta |
| Alarmas activas OLT | `show alarm active` | MEDIUM | Alta |
| Estado de interfaces de uplink | `show interface GigabitEthernet X/X` | MEDIUM | Media |
| ONUs registradas total | `show gpon onu statistics` o conteo por port | MEDIUM | Alta |
| Temperatura OLT | `show system hardware` o `show environment` | LOW | Alta |

**Notas críticas de implementación VSOL:**
- El output SSH es texto plano no estructurado — requiere parseo con regex o patrón específico
- Los comandos exactos varían por versión de firmware; necesita mapeo por modelo
- Latencia SSH puede ser alta (2-5s por comando); optimizar con sesión persistente
- Algunos modelos VSOL permiten SNMP con MIB propietaria — investigar por modelo específico antes de implementar
- La señal Rx/Tx en dBm es el dato más valioso: permite diagnóstico de fibra sin ir al campo

---

### Ubiquiti AirMax / AirFiber

Acceso vía **UISP API REST** (preferido si tienen UISP/UNMS desplegado) o **SSH a AirOS** directamente.

| Metric | Fuente | Campo/Comando | Confidence | Complejidad |
|--------|--------|--------------|------------|-------------|
| Signal level (dBm) | UISP API / AirOS SSH `wstalist` | `signal` | HIGH | Media |
| Remote signal (dBm) | AirOS SSH `wstalist` | `rssi` o `remote-rssi` | HIGH | Media |
| CCQ (%) | UISP API / AirOS SSH | `ccq` | HIGH | Baja |
| TX capacity (Mbps) | UISP API | `txCapacity` | HIGH | Media |
| RX capacity (Mbps) | UISP API | `rxCapacity` | HIGH | Media |
| TX rate actual (Mbps) | AirOS SSH `iwconfig` | tx-rate | MEDIUM | Media |
| Noise floor (dBm) | AirOS SSH `iwconfig` | noise | HIGH | Media |
| CINR / SNR (dB) | UISP API / AirOS | snr o cinr | HIGH | Media |
| Uptime del equipo | UISP API / AirOS SSH `uptime` | uptime | HIGH | Baja |
| Connected clients (AP mode) | AirOS SSH `wstalist` | lista de STAs | HIGH | Media |
| TX/RX bytes (total) | AirOS SSH `ifconfig` | tx-bytes, rx-bytes | HIGH | Baja |
| Firmware version | UISP API | firmwareVersion | HIGH | Baja |
| IP address | UISP API | ipAddress | HIGH | Baja |
| Frequencia (MHz) | AirOS SSH `iwconfig` | Frequency | HIGH | Baja |
| Distance (km) | UISP API | distance | MEDIUM | Baja |

**Nota UISP vs SSH directo:**
- Si BEEPYRED tiene UISP/UNMS, usar su API REST simplifica mucho el trabajo — todos los datos en JSON
- Si no tienen UISP, SSH directo a cada equipo es viable pero requiere parseo de texto
- AirFiber (AF-24, AF-5XHD) tiene comandos SSH diferentes a AirMax (M5, AC, LTU)
- Para AirFiber usar API HTTP interna del equipo (puerto 80/443) además de SSH

---

### Mimosa (B5, B5c, A5x, C5x, etc.)

Acceso vía **API REST nativa** (JSON) — Mimosa provee API documentada para sus equipos.
Confidence: HIGH para modelos B5/B5c; MEDIUM para A5x/C5x (verificar versión firmware).

| Metric | Endpoint REST | Campo JSON | Confidence | Complejidad |
|--------|--------------|-----------|------------|-------------|
| RSSI Local (dBm) | `/api/v1/info/status` | `rssi_local` o `rx_power` | HIGH | Media |
| RSSI Remote (dBm) | `/api/v1/info/status` | `rssi_remote` | HIGH | Media |
| SNR (dB) | `/api/v1/info/status` | `snr` | HIGH | Media |
| Modulacion actual (MCS) | `/api/v1/info/status` | `tx_modulation`, `rx_modulation` | HIGH | Media |
| TX throughput actual (Mbps) | `/api/v1/info/status` | `tx_throughput` | HIGH | Media |
| RX throughput actual (Mbps) | `/api/v1/info/status` | `rx_throughput` | HIGH | Media |
| TX capacity (PHY rate Mbps) | `/api/v1/info/status` | `tx_capacity` | HIGH | Media |
| Uptime (segundos) | `/api/v1/info/status` | `uptime` | HIGH | Baja |
| Temperatura del chip (°C) | `/api/v1/info/status` | `temp` | MEDIUM | Baja |
| Frequencia de operacion (GHz) | `/api/v1/info/status` | `frequency` | HIGH | Baja |
| Channel width (MHz) | `/api/v1/info/status` | `channel_width` | HIGH | Baja |
| MAC address local | `/api/v1/info/status` | `local_mac` | HIGH | Baja |
| Firmware version | `/api/v1/info/status` | `firmware` | HIGH | Baja |
| Link state (UP/DOWN) | `/api/v1/info/status` | `link_state` o derivado de RSSI | HIGH | Baja |

**Notas Mimosa:**
- La API REST requiere autenticación HTTP Basic o token según el firmware
- Mimosa Cloud API (nube Mimosa) existe pero agrega dependencia de conectividad externa; preferir API local
- Modulos A5x (Access Point multipoint) tienen endpoints adicionales para listar clientes conectados
- TDMA frame size y MIMO mode son datos avanzados útiles para diagnóstico de interferencia

---

## Dependencias Entre Features

```
Inventario de equipos
  └─► Polling periódico (necesita saber qué equipos hay)
       ├─► Estado UP/DOWN (resultado del poll)
       │    ├─► Historial de incidentes (registra transiciones UP→DOWN→UP)
       │    │    └─► SLA view / % disponibilidad (calculado desde historial)
       │    └─► Alertas Telegram (triggered al cambiar estado)
       │         └─► Alerta de recovery (complement de alerta de caída)
       ├─► Métricas Mikrotik CPU/RAM/tráfico (del poll RouterOS API)
       │    └─► Gráficas de tendencia (requiere series de tiempo almacenadas)
       ├─► Métricas OLT VSOL (SSH poll → ONUs Rx dBm, estado)
       │    └─► Vista OLT → puertos PON → ONUs jerárquica (requiere estructura parseada)
       │         └─► Histórico Rx dBm por ONU (requiere series de tiempo + ONU identificada)
       ├─► Métricas Ubiquiti (UISP API o AirOS SSH → signal, CCQ)
       │    └─► Umbral configurable por equipo (requiere métricas disponibles)
       └─► Métricas Mimosa (REST API → RSSI, MCS, throughput)

Autenticación básica → Acceso a toda la plataforma (prerequisito transversal)

Topología de dependencias (padre→hijo)
  └─► Correlación de fallas en cascada (require topología definida primero)

Gráficas de tendencia → requiere almacenamiento de series de tiempo (TimeSeries BD)
Alertas por umbral → requiere métricas + definición de thresholds
Modo mantenimiento → requiere sistema de alertas activo primero
```

---

## MVP Recommendation

### Prioridad 1 — Core del NOC (v1 indispensable)

1. Inventario manual de equipos (nombre, IP, tipo, zona)
2. Polling ICMP ping universal (state UP/DOWN para todos)
3. Dashboard unificado con semáforo por equipo
4. Alertas Telegram al caer y al recuperar
5. Historial básico de incidentes (quién cayó, cuándo, cuánto duró)
6. Autenticación de un solo usuario

### Prioridad 2 — Métricas ricas por fabricante (v1 completo)

7. Poll RouterOS API → CPU, RAM, tráfico por interfaz (Mikrotik)
8. Poll SSH VSOL → ONUs online/offline + Rx dBm (OLT GPON)
9. Poll UISP API o AirOS SSH → Signal dBm + CCQ (Ubiquiti)
10. Poll Mimosa REST API → RSSI + throughput (Mimosa)
11. Página de detalle por equipo con métricas en tiempo real
12. Gráficas de últimas 24h por equipo

### Diferenciadores en v1 (si el tiempo lo permite)

13. Filtro por zona/sitio en dashboard
14. Búsqueda rápida de equipo/ONU
15. Modo de mantenimiento (silencio de alertas con duración)
16. Umbral de señal configurable por equipo

### Diferir a v2

- Correlación de fallas en cascada (topología de dependencias)
- Mapa topológico interactivo
- Vista jerárquica OLT → PON → ONU (compleja por parseo VSOL)
- BGP/OSPF status en Mikrotik
- Histórico de señal óptica 30 días
- Alertas por degradación gradual (tendencia)
- Integración Wisphub

---

## Complejidad de Implementación — Resumen

| Nivel | Criterio | Features Representativos |
|-------|----------|--------------------------|
| Baja | < 1 día de trabajo neto | Ping UP/DOWN, inventario CRUD, alerta Telegram on/off, autenticación básica, SLA % calculado |
| Media | 1-3 días | RouterOS API poll + parser, UISP API poll, Mimosa REST poll, gráficas Chart.js, historial de incidentes con filtros |
| Alta | 3+ días | SSH VSOL parser (output no estructurado, varía por modelo), correlación de cascada, mapa topológico, BGP/OSPF status, histórico señal óptica con tendencia |

---

## Sources

- Mikrotik RouterOS API documentation: https://help.mikrotik.com/docs/display/ROS/API (HIGH confidence — documentación oficial)
- Mikrotik RouterOS command reference: https://wiki.mikrotik.com/wiki/Manual:TOC (HIGH confidence)
- VSOL OLT CLI: documentación interna de fabricante / foros ISP Colombia (MEDIUM confidence — documentación fragmentada)
- Ubiquiti AirOS SSH commands: conocimiento consolidado de comunidad ISP (HIGH confidence para comandos base)
- UISP API: https://uisp.ui.com/api-docs (HIGH confidence — Ubiquiti publica swagger docs)
- Mimosa API REST: https://docs.mimosa.co/api (HIGH confidence — documentación oficial pública)
- Patrones NOC para ISPs: conocimiento de dominio consolidado (MEDIUM confidence — sin fuente específica verificada en este run)

**Nota de confidence:** Web tools no disponibles en este entorno de research. Todos los comandos
y endpoints de API son consistentes con documentación oficial conocida, pero deben verificarse
contra la versión exacta de firmware en uso en BEEPYRED antes de implementar.
Especialmente crítico: comandos SSH VSOL varían por modelo y firmware — validar contra el hardware real.
