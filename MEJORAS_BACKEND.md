# Mejoras del backend — auditoría de seguridad y robustez

Fecha: 2026-08-01 (dos rondas)
Alcance: `backend/` únicamente. Punto de partida verificado: 356 pruebas en
verde, cobertura reportada 77 %.

**Segunda ronda** (§ S-08 en adelante y sección «Observaciones cerradas»):
cierre de las cuatro observaciones que la primera ronda dejó marcadas como
teóricas, prueba de extremo a extremo del camino MQTT con broker simulado,
verificación del contrato contra los bytes reales del firmware actual, y
corrección de la medición de cobertura.

Marco de referencia: OWASP ASVS, OWASP WSTG v4.2, OWASP API Security Top 10
(2023), Ley N.° 29733 de Protección de Datos Personales (Perú).

Esta ronda parte del estado posterior a los hallazgos B-01..B-13 y V-01..V-31
ya corregidos; no repite ninguno. Lo que sigue es lo que quedaba flojo.

---

## Resumen de hallazgos

| Id | Severidad | Hallazgo | Estado |
|---|---|---|---|
| S-01 | **Crítica** | El cliente MQTT no se puede ni construir: llamada escrita contra la API de aiomqtt 1.x | Corregido |
| S-02 | **Alta** | La ingesta MQTT muere en silencio ante la primera caída del broker; no hay reconexión | Corregido |
| S-03 | **Alta** | El reporte BPA (RF-13) incluye alertas y trazabilidad de todo el histórico, ignorando el periodo | Corregido |
| S-04 | Media | La longitud mínima de la clave JWT solo se comprobaba en producción | Corregido |
| S-05 | Media | `/api/reportes/bpa` sin validación de rango ni cuota propia (OWASP API4) | Corregido |
| S-06 | Baja | `Cache-Control: no-store` solo en `/api/auth`; el resto de datos personales quedaba cacheable | Corregido |
| S-07 | Baja | `traducir_excepcion_dominio()` es código muerto | Eliminado |
| **S-08** | **Alta** | El reporte BPA se trunca a 10.000 registros **en silencio**: a 30 s de cadencia cubre 3,5 días, luego un reporte mensual omite ~88 % del periodo | Corregido |
| **S-09** | **Media** | `estado_conectividad` y `firmware_version` sin acotar en el contrato IoT, con destino a columnas `String(20)` | Corregido |
| **S-10** | **Media** | La ingesta MQTT no tenía techo de tamaño de mensaje (el REST sí) | Corregido |
| **S-11** | **Media** | La cobertura estaba mal medida: faltaba `concurrency = thread,greenlet` y se reportaba 77 % en vez de 96 % | Corregido |
| O-01 | Media | bcrypt trunca a 72 bytes en silencio (era «teórica»; se demostró reproducible) | Corregido |
| O-02 | **Alta** | El stream SSE sobrevivía al cierre de sesión | Corregido |
| O-03 | Baja | Correo en claro en `audit_logs` (Ley 29733) | Corregido |
| O-04 | Baja | Sin `extra="forbid"` en los esquemas REST | Corregido |
| — | Informativo | IDOR/BOLA: no aplica por diseño (instalación monofarmacia) | Verificado, sin cambio |

---

## S-01 — El cliente MQTT no se puede construir (Crítica)

**Archivo:** `src/infrastructure/mqtt/mqtt_client.py`

**Qué pasaba.** `build_client()` llamaba a `aiomqtt.Client(...)` con
`ssl_context=`, `reconnect=` y `keep_alive=`, y `consumir_mensajes()` iteraba
sobre `client.messages()`. Ninguno de esos nombres existe en aiomqtt 2.x, que
es lo que fija `requirements.txt` (`aiomqtt>=2.3.0`): los parámetros correctos
son `tls_context` y `keepalive`, `reconnect` no existe, y `messages` es una
propiedad, no un método. Comprobado sobre la versión instalada (2.5.1):

```
$ .venv312/bin/python -c "from src.infrastructure.config import Settings; \
    from src.infrastructure.mqtt.mqtt_client import build_client; \
    build_client(Settings(environment='development'))"
TypeError: Client.__init__() got an unexpected keyword argument 'ssl_context'
```

**Por qué importaba.** MQTT es la vía principal de ingesta de la tesis
(RF-05, RF-06). Con este defecto:

- ninguna lectura publicada por un ESP32 llegaba nunca a la base de datos;
- al no pasarse `tls_context`, aunque el constructor hubiera funcionado la
  conexión habría ido en claro, incumpliendo RNF-05;
- el `TypeError` se lanza al construir el cliente, es decir **fuera** del
  `except aiomqtt.MqttError` del `lifespan`, de modo que tumbaba el arranque
  completo del backend en Railway, no solo la ingesta.

Pasó desapercibido porque `mqtt_client.py` no tenía ninguna prueba (48 % de
cobertura, y las 17 sentencias sin cubrir eran exactamente estas) y porque la
suite arranca con `MQTT_ENABLED=false`.

**Qué cambió.** Nombres de parámetro de aiomqtt 2.x, `password` como `str` (no
`bytes`), `client.messages` como propiedad, y documentación de por qué
`build_ssl_context` devuelve un contexto con verificación de certificado.

**Pruebas:** `tests/unit/test_mqtt_client.py` —
`test_build_client_construye_un_cliente_aiomqtt_real`,
`test_build_client_con_tls_habilitado_pasa_un_contexto_ssl`,
`test_build_client_sin_tls_no_configura_contexto_ssl`,
`test_build_ssl_context_verifica_certificado_y_hostname`,
`test_consumir_mensajes_entrega_cada_mensaje_al_manejador`.

---

## S-02 — La ingesta MQTT muere en silencio ante una caída del broker (Alta)

**Archivos:** `src/infrastructure/mqtt/mqtt_client.py`, `src/interface/main.py`

**Qué pasaba.** `consumir_mensajes()` protegía con `try/except` el *cuerpo* del
bucle (un mensaje malformado no tumbaba el consumidor, hallazgo AI-02 ya
corregido), pero no el `async for` en sí. Una `MqttError` del iterador —que es
lo que ocurre cuando el broker cierra la conexión— terminaba la tarea. No había
reintento, ni registro en el log, ni efecto visible: el backend seguía
respondiendo por HTTP con normalidad mientras dejaba de recibir lecturas de los
refrigeradores indefinidamente.

**Por qué importaba.** Es el peor modo de fallo posible en este sistema: un
backend caído se detecta; un backend que responde 200 mientras la cadena de
frío deja de vigilarse, no. EMQX Cloud Serverless es un servicio gestionado
externo, así que las desconexiones son esperables, no excepcionales.

**Qué cambió.** Nuevo `consumir_con_reconexion()`: bucle que reabre la sesión
con espera exponencial (1 s → 60 s), registra cada caída, y distingue
`CancelledError` (apagado ordenado, se propaga) de `MqttError` y del resto de
excepciones. `mqtt_session()` pasa a ceder la tarea consumidora en lugar de un
cliente concreto, porque con reconexión el cliente cambia en cada reintento.
En `main.py`, el `lifespan` captura `Exception` y no solo `MqttError`, para que
un fallo de construcción o de configuración TLS no impida arrancar la API.

**Pruebas:** `tests/unit/test_mqtt_client.py` —
`test_la_ingesta_se_reconecta_tras_una_caida_del_broker`,
`test_la_reconexion_tambien_sobrevive_a_errores_no_mqtt`,
`test_mqtt_session_cancela_la_tarea_al_salir`,
`test_un_mensaje_que_falla_no_detiene_el_consumo_de_los_siguientes`.

---

## S-03 — El reporte BPA no se ciñe al periodo solicitado (Alta)

**Archivos:** `src/application/use_cases/exportar_reporte_bpa.py`,
`src/application/use_cases/exportar_reporte_bpa_pdf.py`,
`src/domain/repositories/i_alerta_repository.py`,
`src/domain/repositories/i_trazabilidad_repository.py`,
`src/infrastructure/database/repositories/alerta_repository.py`,
`src/infrastructure/database/repositories/trazabilidad_repository.py`

**Qué pasaba.** Ambos casos de uso acotaban las lecturas por fecha:

```python
lecturas = await self._lectura_repository.listar(
    device_id=device_id, desde=fecha_desde, hasta=fecha_hasta, limite=10_000)
```

pero no las otras dos colecciones:

```python
alertas = await self._alerta_repository.listar(device_id=device_id, limite=10_000)
trazabilidad = await self._trazabilidad_repository.listar(device_id=device_id, limite=10_000)
```

La causa es que `IAlertaRepository.listar` e `ITrazabilidadRepository.listar`
ni siquiera aceptaban parámetros de fecha, a diferencia de
`ILecturaRepository.listar`.

**Por qué importaba.** RF-13 y el Manual de BPA. Un reporte "de enero"
adjuntaba las excursiones térmicas y los eventos de trazabilidad de todos los
meses registrados. Un documento de cumplimiento que atribuye hechos a un
periodo que no les corresponde no es evidencia válida ante una inspección de
DIGEMID: sobredeclara incumplimientos en periodos limpios y difumina los reales.
Afectaba por igual al JSON y al PDF, que es el entregable formal (HU-38).

**Qué cambió.** `desde`/`hasta` añadidos a las dos interfaces de dominio y a
sus implementaciones SQLAlchemy, y propagados desde ambos casos de uso. Las
alertas se filtran por `created_at` y la trazabilidad por `timestamp` (el
instante del hecho registrado, que es el campo que el propio reporte muestra al
auditor).

**Pruebas:** `tests/integration/test_reportes_rango_periodo.py` —
`test_el_reporte_no_incluye_alertas_ni_trazabilidad_fuera_del_periodo` y su
contraprueba `test_el_reporte_si_incluye_lo_ocurrido_dentro_del_periodo`.
Ambas fallaban antes del arreglo.

---

## S-04 — Longitud mínima de la clave JWT solo exigida en producción (Media)

**Archivos:** `src/infrastructure/config.py`, `tests/unit/test_jwt_handler.py`

**Qué pasaba.** `_validar_secretos_en_produccion` rechazaba claves de menos de
32 caracteres, pero únicamente con `environment="production"`. En desarrollo y
en pruebas se aceptaba cualquier longitud. La suite lo dejaba ver:

```
InsecureKeyLengthWarning: The HMAC key is 15 bytes long, which is below the
minimum recommended length of 32 bytes for SHA256. See RFC 7518 Section 3.2.
```

El origen eran las fixtures `Settings(jwt_secret_key="clave-de-prueba")` (15
bytes) y `"otra-clave-distinta"` (19) de `test_jwt_handler.py`.

**Por qué importaba.** Dos cosas distintas. Una, RFC 7518 §3.2: con una clave
HMAC más corta que la salida de SHA-256, forjar una firma es más barato que
romper el hash. Dos, y más práctico: un aviso genérico de PyJWT entre otros 2400
warnings de la suite es indistinguible del ruido de librerías, así que una clave
débil podía viajar a un `.env` de despliegue sin que nadie lo notara. La
comprobación tenía que ser del proyecto, no de la dependencia.

**Qué cambió.** Constante `LONGITUD_MINIMA_CLAVE_JWT = 32` y validador
`_validar_longitud_clave_jwt` que se ejecuta en **todos** los entornos: en
producción sigue siendo error de arranque; fuera de producción emite un
`ClaveJWTDebilWarning` propio y atribuible. La longitud se mide en **bytes**
(`.encode()`), no en caracteres, que es lo que consume el HMAC. Las fixtures de
prueba pasan a usar claves conformes.

Resultado: `InsecureKeyLengthWarning` desaparece por completo de la suite
(`pytest -W default | grep -c InsecureKeyLength` → `0`).

**Pruebas:** `tests/unit/test_config_clave_jwt.py` (5 casos, incluido
`test_la_longitud_se_mide_en_BYTES_no_en_caracteres`).

---

## S-05 — Reporte BPA sin validación de rango ni cuota propia (Media)

**Archivo:** `src/interface/api/reportes_router.py`

**Qué pasaba.** Tres huecos en el endpoint más caro de la API:

1. El endpoint PDF validaba `fecha_desde <= fecha_hasta`; el JSON no, y
   devolvía 200 con un reporte de un periodo imposible.
2. Ninguno acotaba la *amplitud* del periodo. Una sola petición podía pedir la
   materialización de hasta 10.000 lecturas + 10.000 alertas + 10.000 registros
   de trazabilidad, serializados a objetos Pydantic en memoria.
3. Ninguno tenía cuota propia. Solo aplicaba el límite global por IP
   (240 req/min), que trata igual un `GET /health` que una exportación
   completa. `/api/trazabilidad/verificar` sí tenía cuota por usuario (5/min);
   los reportes, no.

**Por qué importaba.** OWASP API4:2023 (consumo de recursos sin restricción).
El despliegue objetivo es Railway Hobby: 1 vCPU y **512 MB de RAM** compartidos
con el resto de la aplicación, el modelo Random Forest cargado en memoria y las
colas SSE. Es el vector más barato para dejar el sistema sin servicio, y no
requiere ninguna credencial especial: basta una cuenta de farmacéutico legítima.

**Qué cambió.** Helper `_validar_rango()` compartido por ambos endpoints, que
valida el orden y rechaza periodos de más de `MAX_DIAS_RANGO_REPORTE = 366`
días (un ejercicio anual, que es el horizonte de un reporte BPA). Cuota
`limitar_por_usuario(..., 10, 60)` en los dos.

**Pruebas:** `tests/integration/test_reportes_rango_periodo.py` —
`test_rango_invertido_se_rechaza_en_el_reporte_json`,
`test_periodo_desmesurado_se_rechaza`,
`test_el_reporte_bpa_tiene_cuota_propia_por_usuario`. Las tres fallaban antes.

---

## S-06 — Datos personales cacheables fuera de `/api/auth` (Baja)

**Archivo:** `src/interface/api/security_headers.py`

**Qué pasaba.** `Cache-Control: no-store` se emitía solo para rutas bajo
`/api/auth`. El resto de la API —historial térmico, `audit_logs`, reportes BPA,
listado de usuarios— salía sin directiva de caché.

**Por qué importaba.** Ley N.° 29733: esos cuerpos contienen datos personales
(nombres, correos, IP de origen de cada acción) y datos de la operación
sanitaria. Sin `no-store`, una caché intermedia puede retenerlos, lo que es una
difusión no prevista en el consentimiento que la propia HU-44 recoge.

**Qué cambió.** La directiva se aplica a todo lo que empieza por `/api`. El
motivo queda documentado en el propio código.

**Prueba:** `tests/integration/test_seguridad_api.py::test_los_datos_personales_de_la_api_tampoco_son_cacheables`.

---

## S-07 — Código muerto en la capa de interface (Baja)

`traducir_excepcion_dominio()` en `src/interface/api/deps.py` no se invocaba
desde ningún punto del código ni de las pruebas (verificado por búsqueda en
`src/` y `tests/`). Cada router traduce sus excepciones de dominio en línea.
Se eliminó, junto con el import de `RecursoNoEncontradoError` que solo él usaba.
Sin prueba asociada: es una eliminación, y la suite completa en verde es la
comprobación de que nada dependía de él.

---

## Verificaciones realizadas sin hallazgo

Se documentan para que no se vuelvan a revisar y para poder responder si el
jurado pregunta.

**IDOR / BOLA (OWASP API1).** No aplica por diseño. El sistema es una
instalación monofarmacia: no existe columna de tenant ni de propietario en
`thermal_readings`, `thermal_alerts` ni `devices`, y todos los roles
autorizados ven legítimamente todos los dispositivos de la misma farmacia. Los
dos recursos que sí tienen dueño se consultan siempre acotados por el usuario
autenticado, nunca por un id recibido del cliente: el checklist BPA
(`ConsultarChecklistBPAUseCase.obtener_del_dia(usuario.id, ...)` y
`listar_historial(usuario.id, ...)`) y los datos de privacidad. No se encontró
ningún endpoint que acepte un `usuario_id` del cliente para leer o escribir
recursos ajenos.

**Inyección SQL en filtros dinámicos.** Todos los filtros (`device_id`,
`nivel_riesgo`, `estado_conectividad`, `tipo_evento`, fechas) se construyen con
cláusulas `where()` de SQLAlchemy con parámetros ligados. No hay interpolación
de cadenas en ninguna consulta de los repositorios.

**Paginación.** Todos los listados acotan con
`Query(default=..., ge=1, le=1000)` (`le=365` en el historial de checklist).
No se encontró ningún endpoint con paginación abierta.

**Enumeración de usuarios y timing.** `AutenticarUsuarioUseCase` verifica
contra un hash señuelo cuando el email no existe, y devuelve el mismo mensaje
en los tres casos de rechazo (email inexistente, contraseña incorrecta, usuario
desactivado). El endpoint de Google devuelve un mensaje único para cualquier
causa de rechazo; cubierto ahora por
`test_el_mensaje_de_error_no_distingue_el_motivo_del_rechazo`.

**Separación de audiencias JWT.** El ticket SSE (`aud` propia, viaja por la
URL) no vale como Bearer y el token de acceso no vale como ticket SSE.
Verificado en los dos sentidos en `test_deps_autenticacion.py`.

**Clientes SSE lentos y desconexiones.** `SSEBroadcaster.publicar` descarta el
evento para la cola llena en lugar de esperar, de modo que un navegador que
dejó de leer no congela la difusión ni el pipeline de ingesta; el generador
libera la suscripción en su `finally`. El comportamiento era correcto pero no
estaba cubierto por ninguna prueba: ahora lo está (`test_sse_broadcaster.py`).

**Índices de los filtros de RF-12.** Ya cubiertos por la migración
`0006_checklist_calibracion_indices` (hallazgo B-11): `(device_id, timestamp DESC)`
en `thermal_readings`, `(device_id, created_at DESC)` en `thermal_alerts`,
`created_at DESC` en `traceability_records` y en `audit_logs`. Sin cambios.

**Sin cambios en migraciones.** Los filtros de fecha añadidos en S-03 usan
columnas ya indexadas o ya existentes; no hizo falta ninguna migración nueva.

### Observaciones declaradas como teóricas en la 1.ª ronda

**Todas cerradas en la segunda ronda**; ver «Las cuatro observaciones
«teóricas», cerradas». Se conserva aquí la redacción original para que se vea
qué se dio por teórico y en qué se quedó, porque una de ellas (bcrypt) resultó
reproducible en cuanto se comprobó en vez de razonarla.

- **bcrypt trunca a 72 bytes.** `UsuarioCreateRequest.password` admite hasta
  128 caracteres, pero bcrypt solo considera los primeros 72 bytes. Dos
  contraseñas muy largas que compartan prefijo serían equivalentes. Requiere
  contraseñas de más de 72 bytes, que ningún usuario del sistema tiene.
  No se cambió para no alterar los hashes ya almacenados.
- **Una sesión SSE ya abierta sobrevive al `logout`.** La revocación por `jti`
  se comprueba al abrir el stream, no durante. La ventana máxima es la vida del
  stream. No se cambió porque cerrarlo exigiría consultar el store de
  revocación en cada latido, a cambio de un beneficio marginal en un sistema
  de tres usuarios.
- **`audit_logs` registra el email tecleado en cada `LOGIN_FALLIDO`**, incluso
  si no corresponde a ningún usuario. Es un dato personal de un tercero. Se
  mantiene: es la evidencia forense que da sentido al registro, y RF-16 exige
  precisamente esa trazabilidad.
- **Los esquemas Pydantic no declaran `extra="forbid"`.** Un campo de más se
  ignora en silencio en lugar de rechazarse. No hay asignación masiva real:
  todos los casos de uso construyen las entidades campo a campo desde el
  esquema, nunca por desempaquetado del cuerpo recibido. Es defensa en
  profundidad no aplicada, no una vulnerabilidad.

---

# Segunda ronda

## S-08 — El reporte BPA se truncaba en silencio (Alta)

**Archivos:** `src/application/use_cases/exportar_reporte_bpa.py`,
`exportar_reporte_bpa_pdf.py`, `src/interface/api/schemas.py`,
`src/interface/api/reportes_router.py`, `src/infrastructure/pdf/generador_pdf.py`

**Qué pasaba.** Las tres consultas del reporte llevaban `limite=10_000`. Ese
tope no se declaraba en ninguna parte de la respuesta ni del PDF.

La cuenta es la que convierte esto en un defecto serio. `config.h` del firmware
fija `INTERVALO_LECTURA_MS 30000`, es decir 2.880 lecturas por dispositivo y
día:

```
Lecturas/día a 30 s: 2880
El tope de 10.000 cubre 3.47 días
Un reporte mensual necesita 86400 lecturas
```

Un reporte BPA mensual mostraba unos 3,5 días y omitía el ~88 % restante **sin
decirlo**.

**Por qué importaba.** Es el mismo problema de fondo que S-03 pero peor: allí el
reporte incluía datos de más, aquí falta la mayoría y el documento se presenta
como si estuviera completo. Un reporte de cumplimiento que omite registros en
silencio no es evidencia; es evidencia engañosa. Ante una inspección de DIGEMID,
el auditor daría por completo un histórico que no lo es, y las estadísticas del
encabezado (% de tiempo en rango, temperatura mínima y máxima) se calculan sobre
esa muestra parcial sin ninguna advertencia.

**Por qué no basta con subir el tope.** Está puesto por memoria, y se midió:

```
Objetos Pydantic en memoria: 42.9 MB (pico 42.9 MB)
Tras serializar: 55.7 MB (pico 80.9 MB)
Tamano del cuerpo JSON: 12.6 MB
```

Un solo reporte lleno alcanza ~81 MB de pico y devuelve 12,6 MB, en una
instancia de 512 MB compartidos con el modelo Random Forest, el pool de
conexiones y las colas SSE. Subir el tope a 86.400 multiplicaría eso por ocho.
La decisión es mantener el techo y **declararlo**.

**Qué cambió.** `listar_detectando_truncamiento()` pide `limite + 1` registros:
si vuelve el extra, hay más datos de los que caben, se descarta y se marca la
bandera. Es mucho más barato que un `COUNT(*)` sobre la serie temporal y basta
para poder declarar el recorte. La respuesta JSON expone `truncado`,
`lecturas_truncadas`, `alertas_truncadas`, `trazabilidad_truncada` y
`limite_por_coleccion`; el PDF abre con un aviso destacado —antes del resumen,
no en una nota al pie— que dice que el documento está INCOMPLETO y recomienda
dividir el periodo en rangos más cortos.

El tope informado lo declara el caso de uso (`limite_aplicado`), no el router,
para que el valor publicado no pueda desviarse del realmente aplicado.

**Pruebas:** `tests/integration/test_reporte_truncamiento.py` (8 casos:
detección con el registro extra, caso frontera exacto, propagación al JSON, al
PDF, y las dos contrapruebas de que un reporte completo no se marca).

---

## S-09 y S-10 — Contrato IoT↔backend (Media)

Verificación pedida tras los cambios del firmware (timestamp UTC, validación de
integridad del payload, credenciales desde NVS).

**Método.** No se comparó leyendo código. Se compiló el serializador real del
firmware en el host —`PayloadCore.cpp` y `Reloj.cpp` son independientes de
Arduino a propósito— y se validaron sus bytes literales contra el esquema
Pydantic:

```
{"device_id":"FARM-01-CDL","timestamp":"2026-07-29T10:34:56Z","estado_conectividad":"online","firmware_version":"1.4.0","temperatura_interna":4.53,"temperatura_ambiental":5.21,"humedad_ambiental":62.40,"apertura_refrigerador":true,"duracion_apertura_segundos":42}
{"device_id":"FARM-01-CDL","timestamp":"2026-07-29T10:35:26Z","estado_conectividad":"offline","firmware_version":"1.4.0","temperatura_interna":null,"temperatura_ambiental":null,"humedad_ambiental":null,"apertura_refrigerador":false,"duracion_apertura_segundos":0}
```

**Resultado: el contrato está alineado.** Ambos payloads se aceptan tal cual.
En concreto:

| Aspecto | Firmware | Backend | Estado |
|---|---|---|---|
| Campos emitidos | 9 | los 9 declarados | ✓ |
| Formato de fecha | `YYYY-MM-DDTHH:MM:SSZ` | `datetime` Pydantic v2 → tz-aware UTC | ✓ |
| Sensor caído | `null` explícito, nunca `0.0` | `float \| None` | ✓ |
| DS18B20 (`temperatura_interna`) | `[-55, 125]` | `ge=-55.0, le=125.0` | ✓ |
| SHT31 temp (`temperatura_ambiental`) | `[-40, 125]` | `ge=-40.0, le=125.0` | ✓ |
| SHT31 humedad | `[0, 100]` | `ge=0.0, le=100.0` | ✓ |
| Tamaño | descarta > 512 B | (ver S-10) | corregido |
| `duracion_apertura_segundos` | `uint32_t`, siempre presente | `int, ge=0` | ✓ |

Los rangos coinciden exactamente, que es lo que garantiza que ninguna lectura
válida se pierda por desajuste. También se comprobó que el redondeo a dos
decimales del firmware (`%.2f`) no puede empujar un valor válido fuera de rango.

**S-09 (corregido).** Dos campos quedaban sin acotar en el backend:

- `estado_conectividad: str` libre, cuando el firmware solo emite `"online"` u
  `"offline"`. Una cadena larga pasaba la validación y llegaba hasta la columna
  `String(20)`, donde PostgreSQL la rechaza con un error de escritura en lugar
  de un 422 en el borde. Ahora es `Literal["online", "offline"]`.
- `firmware_version: str | None` sin tope, cuando `EventoDispositivoPayload` ya
  lo limitaba a 20 y `devices.firmware_version` es `String(20)` —
  inconsistencia dentro del mismo archivo. Ahora `max_length=20`.

Ambos se aplicaron también a `LecturaIngestRequest` (vía REST): las dos vías
deben aceptar exactamente lo mismo, o el contrato se bifurca según el transporte.

**S-10 (corregido).** La ingesta MQTT no tenía ningún techo de tamaño. El
cuerpo de las peticiones REST sí lo tiene (`max_body_bytes`, 64 KB, aplicado por
middleware ASGI), pero los mensajes del broker no atraviesan esa pila. Quien
tuviera credenciales del broker podía forzar la materialización de un mensaje
arbitrariamente grande. Se añade `MAX_BYTES_PAYLOAD_MQTT = 5 KB` —diez veces el
máximo legítimo de 512 B— comprobado **antes** de deserializar.

**Nada que tocar del lado del firmware.** El contrato ya era correcto; los
cambios son todos de endurecimiento en el backend.

**Pruebas:** `tests/integration/test_contrato_firmware_bytes_reales.py` (10
casos sobre los bytes literales, incluidos los límites de rango de cada sensor y
una guardia de que ningún campo emitido falte en el esquema).

---

## S-11 — La cobertura estaba mal medida (Media)

**Archivo:** `.coveragerc`

**Qué pasaba.** Varios casos de uso aparecían muy por debajo de lo que sus
pruebas realmente ejercitan. El más llamativo: `autenticar_usuario.py` al 68 %,
con el cuerpo entero de `execute()` marcado como no cubierto, cuando **todas**
las pruebas de login lo recorren.

No era código sin probar: era instrumentación. `TestClient` levanta la
aplicación ASGI en su propio hilo y SQLAlchemy async ejecuta el ORM dentro de
greenlets; sin declararlo, coverage pierde el rastro.

```
# antes
src/application/use_cases/autenticar_usuario.py      28      9    68%   33-43
# después de añadir concurrency = thread,greenlet
src/application/use_cases/autenticar_usuario.py      28      1    96%   40
```

**Por qué importaba.** El 77 % es una cifra que la documentación de la tesis
cita como indicador de calidad (§4.6). Estaba **subestimada**, no inflada, que
es el sentido menos dañino del error — pero seguía siendo una medición
incorrecta, y la parte que aparecía sin cubrir habría llevado a escribir
pruebas de relleno para código que ya estaba probado.

**Qué cambió.** `concurrency = thread,greenlet` en `.coveragerc`. La cobertura
real pasa a **96 %**, sin añadir una sola prueba por ese cambio.

---

## Las cuatro observaciones «teóricas», cerradas

La primera ronda las dejó anotadas sin actuar. Se revisó cada una por separado.

### O-01 — bcrypt trunca a 72 bytes (era teórica; **resultó reproducible**)

Se comprobó antes de decidir:

```
len largo: 80 len variante: 88
hash ok
verifica la variante con distinta cola?: True
```

Dos contraseñas distintas que comparten los primeros 72 bytes son
intercambiables al iniciar sesión. No era teórico, y el esquema lo invitaba
activamente al admitir `max_length=128`.

**Decisión: corregir rechazando, no truncando.** `PASSWORD_MAX_BYTES = 72`
validado en el borde, medido en **bytes** (una contraseña con acentos ocupa más
bytes que caracteres). Un 422 explícito es preferible a una contraseña que
«funciona» con una cola distinta a la que el usuario escribió. No se cambia el
algoritmo de hash: eso invalidaría los hashes ya almacenados, y toda contraseña
de 72 bytes o menos se comporta exactamente igual que antes.

### O-02 — El stream SSE sobrevivía al logout (era teórica; **es la de más peso**)

Coincido con la valoración: es la más grave de las cuatro. La tesis presenta la
revocación de JWT como control de seguridad (RF-17), y un caudal de datos
térmicos que sigue fluyendo después de cerrar sesión la contradice de frente.
La revocación se comprobaba **solo al abrir** el stream, y un SSE vive horas.

**Decisión: corregir atando el stream a la sesión.** El ticket SSE incorpora el
`jti` del access token que lo pidió (claim `ptk`). Con eso:

- al **emitir** el stream se rechaza un ticket cuya sesión ya se cerró;
- **durante** el stream se comprueba la revocación en cada vuelta del bucle
  (a lo sumo cada 15 s, que es el intervalo del keep-alive), y al detectarla se
  corta y se libera la suscripción.

Un ticket sin `ptk` (emitido antes de este cambio) no corta el stream, por
compatibilidad.

### O-03 — Correo en claro en `audit_logs` (Ley 29733)

**Decisión: minimizar, no eliminar.** Los dos extremos eran malos: quitar el
dato deja RF-16 sin valor forense; conservarlo entero retiene indefinidamente un
dato personal que puede no pertenecer a ningún usuario del sistema —un error de
escritura, o la dirección de un tercero usada por quien ataca— en una bitácora
**inmutable por diseño**, donde no hay rectificación ni supresión posibles.

Se guarda `v***@otrodominio.example`. Conserva lo que da valor a la bitácora
(qué dominio se ataca, correlación entre intentos porque la máscara es estable,
IP de origen) y descarta la identificación directa del titular. Además, en
`LOGIN_EXITOSO` el correo se elimina por completo: `usuario_id` ya identifica al
titular de forma estable, así que repetirlo era dato redundante.

### O-04 — `extra="forbid"` en los esquemas REST

**Decisión: aplicar, con la severidad correcta.** Conviene precisar la
observación original: el contrato **MQTT** (`LecturaPayload`,
`EventoDispositivoPayload`) ya lo declaraba; lo que faltaba era en los esquemas
de petición **REST**. Se revisó de nuevo que no hubiera asignación masiva real —
ningún caso de uso construye entidades desempaquetando el cuerpo recibido, todos
copian campo a campo— así que **no era una vulnerabilidad explotable** y no se
le sube la severidad. Lo que sí resuelve es que un cliente desalineado falle de
forma ruidosa (422) en lugar de silenciosa.

Se aplica mediante una base común `_PeticionEstricta` a los 11 esquemas de
petición; las respuestas se dejan intactas.

**Pruebas de las cuatro:** `tests/integration/test_observaciones_cerradas.py`
(15 casos), más `test_cerrar_sesion_corta_el_stream_abierto` y
`test_un_stream_sin_sesion_asociada_no_se_corta` en `tests/unit/test_sse_broadcaster.py`.

---

## Prueba de extremo a extremo del camino MQTT

**Archivo:** `tests/integration/test_mqtt_pipeline_e2e.py` (13 casos)

Las pruebas de contrato previas llamaban directamente a
`_procesar_mensaje_mqtt`, **saltándose por completo** `mqtt_client.py`. Ésa es
la razón concreta de que S-01 sobreviviera meses con la suite en verde.

Ahora los mensajes entran por donde entran en producción —`consumir_mensajes` /
`consumir_con_reconexion` sobre un doble de broker que imita la interfaz real de
aiomqtt 2.x (`messages` como propiedad, context manager asíncrono)— y recorren:
payload del ESP32 → validación Pydantic → clasificación IA → persistencia →
alerta → evento SSE.

| Caso | Qué fija |
|---|---|
| `test_lectura_normal_recorre_todo_el_camino` | Persistencia + veredicto de IA + evento SSE |
| `test_excursion_critica_genera_alerta_y_evento_sse` | RF-08/RF-09/RF-11 a 19,9 °C |
| `test_la_lectura_queda_encadenada_en_la_trazabilidad` | RF-14: eslabón SHA-256 por lectura |
| `test_una_rafaga_de_lecturas_se_procesa_en_orden` | Volcado del buffer LittleFS (RF-06) |
| `test_payload_malformado_no_detiene_el_consumo` | JSON truncado y basura entre lecturas válidas |
| `test_payload_con_campo_desconocido_se_descarta_sin_romper` | Contrato cerrado sin matar el consumidor |
| `test_payload_desmesurado_se_rechaza_antes_de_deserializar` | S-10 |
| `test_device_id_que_no_coincide_con_el_topico_se_descarta` | Anti-suplantación |
| `test_la_ingesta_se_reanuda_tras_una_caida_del_broker` | S-02 sobre el camino real |
| `test_al_conectar_se_suscribe_a_lecturas_y_a_eventos` | Olvidar una suscripción no rompe nada visible |
| `test_dispositivo_no_provisionado_se_rechaza_y_se_audita` | El rechazo queda en `audit_logs`, no solo en el log |
| `test_lectura_con_timestamp_futuro_se_rechaza_y_se_audita` | Antedatar evidencia no entra en la cadena |

**Guardia específica contra la reaparición de S-01.** Un doble de broker imita
la interfaz, no la valida: por definición no puede detectar que el constructor
real cambió. Por eso se añade
`test_los_parametros_de_build_client_existen_en_la_version_instalada`, que
contrasta los nombres de parámetro que usa `build_client` contra
`inspect.signature(aiomqtt.Client.__init__)` de la librería instalada. Si una
futura actualización de aiomqtt renombra uno, falla en CI y no en el despliegue.

---

## Rendimiento y memoria (Railway 512 MB)

Medido, no estimado. Ver S-08 para las cifras del reporte BPA (~81 MB de pico,
12,6 MB de cuerpo) y la decisión resultante.

| Camino | Situación |
|---|---|
| Historial (`GET /api/lecturas`) | Acotado a `le=1000` por página. 1.000 lecturas ≈ 4,3 MB de pico según la misma medición proporcional. Sin cambios. |
| Reporte BPA | Techo mantenido y **declarado** (S-08); rango máximo de 366 días y cuota de 10/min por usuario (S-05, primera ronda). |
| Ingesta MQTT | Techo de 5 KB por mensaje (S-10). |
| Colas SSE | 100 mensajes por suscriptor, descarte al llenarse, liberación al desconectar — verificado en `test_sse_broadcaster.py`. |
| Índices | Los de B-11 cubren los filtros de RF-12; los nuevos filtros de fecha (S-03) reutilizan `(device_id, timestamp DESC)` y `created_at DESC`. Sin migraciones nuevas. |

**Riesgo residual declarado, no corregido:** la cuota de 10 reportes/min por
usuario no impide la **concurrencia**. Tres peticiones simultáneas de reportes
llenos sumarían ~240 MB de pico. Con tres usuarios en total y una operación que
el frontend lanza de una en una, no se consideró justificado añadir un semáforo
de concurrencia; queda anotado por si el número de usuarios crece.


---

## Cobertura

`.coveragerc` hace dos cosas, por motivos distintos:

1. **`concurrency = thread,greenlet`** — corrige la medición (S-11). Sin esto,
   coverage perdía el rastro del código ejecutado dentro del hilo de
   `TestClient` y de los greenlets de SQLAlchemy async, y daba por no cubierto
   código que las pruebas sí recorren.
2. **`omit`** de `train_model.py`, `train_model_v2.py` y `train_model_v3.py` —
   son scripts de entrenamiento offline que se ejecutan a mano para producir el
   artefacto `.pkl`; no forman parte del servicio. Las métricas del modelo
   (RNF-04) se validan sobre el artefacto entrenado en
   `test_random_forest_service*.py`, no sobre estos scripts.

| Medida | Inicio (1.ª ronda) | Fin (1.ª ronda) | Fin (2.ª ronda) |
|---|---|---|---|
| Pruebas | 356 | 397 | **450** |
| Cobertura reportada entonces | 77 % | 86 % | — |
| Cobertura **bien medida** | — | — | **96 %** (3582 sent., 140 sin cubrir) |

Conviene ser explícito sobre por qué el salto es tan grande: **la mayor parte no
viene de las pruebas nuevas, sino de S-11**. El 77 % de partida estaba mal
medido. Las 94 pruebas añadidas en las dos rondas cubren código que
efectivamente no se ejercitaba —`mqtt_client.py`, el verificador de Google, el
broadcaster SSE, los envíos de notificación— pero el grueso de la diferencia es
que ahora se mide bien.

Módulos con mejora atribuible a pruebas nuevas (no a la corrección de medida):

| Módulo | Antes | Después |
|---|---|---|
| `infrastructure/mqtt/mqtt_client.py` | 48 % | 98 % |
| `infrastructure/security/google_token_verifier.py` | 44 % | 100 % |
| `interface/api/sse_broadcaster.py` | 61 % | 100 % |
| `interface/api/sse_router.py` | 47 % | 91 % |
| `infrastructure/notifications/notificacion_service.py` | 79 % | 95 % |

### Lo que queda sin cubrir y no merece más

- `generador_pdf.py` (89 %): ramas de formateo de celdas con valores nulos. Son
  variantes tipográficas; probarlas sería fijar la maquetación, no el
  comportamiento.
- `main.py` (92 %): el `lifespan` con MQTT habilitado, que exige un broker real.
  El resto del módulo sí está cubierto por la prueba de extremo a extremo.
- `session.py` (85 %): dos líneas de construcción del engine de producción.
- `rate_limiter.py` (88 %): ramas de poda del diccionario cuando se alcanza
  `max_claves`; el comportamiento observable ya está cubierto.

Ficheros de prueba nuevos (2.ª ronda):

- `tests/integration/test_mqtt_pipeline_e2e.py` (13) — camino completo MQTT
- `tests/integration/test_observaciones_cerradas.py` (15) — O-01..O-04
- `tests/integration/test_contrato_firmware_bytes_reales.py` (10) — S-09/S-10
- `tests/integration/test_reporte_truncamiento.py` (8) — S-08
- `tests/unit/test_notificacion_envio.py` (5) — HU-23

## Salida de las comprobaciones

Intérprete: `/Volumes/Universidad/Tesis Code/backend/.venv312/bin/python`.
Salida de la verificación final (segunda ronda).

### Suite completa con cobertura

```
$ .venv312/bin/python -m pytest -q --cov=src --cov-report=term
...
TOTAL                                        3582    140    96%
450 passed, 2421 warnings in 134.97s (0:02:14)
```

### Análisis estático

```
$ .venv312/bin/python -m ruff check .
All checks passed!
```

### Migraciones desde cero

```
$ DATABASE_URL="sqlite+aiosqlite:////tmp/verif2.db" ENVIRONMENT=test \
  MQTT_ENABLED=false .venv312/bin/python -m alembic upgrade head
INFO  [alembic.runtime.migration] Running upgrade  -> 0001_initial_schema, ...
INFO  [alembic.runtime.migration] Running upgrade 0001_initial_schema -> 0002_thermal_readings_dedup, ...
INFO  [alembic.runtime.migration] Running upgrade 0002_thermal_readings_dedup -> 0003_lecturas_modelo_ia, ...
INFO  [alembic.runtime.migration] Running upgrade 0003_lecturas_modelo_ia -> 0004_ia_correcciones_p1, ...
INFO  [alembic.runtime.migration] Running upgrade 0004_ia_correcciones_p1 -> 0005_hu43_47_ciclo_vida, ...
INFO  [alembic.runtime.migration] Running upgrade 0005_hu43_47_ciclo_vida -> 0006_checklist_calibracion_indices, ...
```

No se añadió ninguna migración en ninguna de las dos rondas.

### Auditoría de dependencias

```
$ .venv312/bin/python -m pip_audit --progress-spinner off
No known vulnerabilities found
```

### Integridad de la arquitectura DDD

```
$ grep -rn "from src.infrastructure\|from src.interface" src/domain/
OK: dominio no importa infraestructura ni interface
```

### Ausencia del aviso de clave HMAC débil (S-04)

```
$ .venv312/bin/python -m pytest -q -W default 2>&1 | grep -c InsecureKeyLength
0
```

## Nota sobre S-01 y el proceso

S-01 y S-02 viven en el mismo archivo, y es el único módulo de infraestructura
del backend que no tenía una sola prueba. No es casualidad: la ingesta MQTT
lleva meses rota en cualquier despliegue real y la suite verde no podía
detectarlo porque arranca con `MQTT_ENABLED=false` y nunca ejercitaba
`build_client`. Es el mismo patrón que el workflow de CI documentado en V-30
identificó para el firmware. Conviene tenerlo presente antes de la validación
técnica con hardware (OE4): las lecturas por MQTT del ESP32 no habrían llegado
nunca al backend, y el síntoma —dashboard vacío— se habría atribuido al
firmware o al broker.
