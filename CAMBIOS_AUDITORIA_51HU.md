# Cambios aplicados — auditoría contra el backlog de 51 HU finales (2026-08-30)

**Fecha de esta pasada:** 2026-09-02
**Punto de partida:** código congelado el 2026-08-01 (commit `68c4005`), auditado contra un backlog de 51 historias de usuario finalizado el 2026-08-30 — posterior al código. El informe completo de la auditoría (qué faltaba y por qué) vive en `documentacion/Documentacion-general/audit_51hu.html`. Este archivo documenta **qué se implementó para cerrar esos hallazgos**, no repite el diagnóstico.

**Resultado:** 535 tests pasan (`pytest -q`), 0 fallos. Los 5 errores restantes en `test_migraciones.py` son un problema preexistente de Windows (un archivo SQLite temporal queda bloqueado en el teardown del test) — no relacionado con este trabajo, confirmado como preexistente antes de tocar nada.

---

## HU-05 — Estructuración versionada de telemetría

- `LecturaPayload` (`src/infrastructure/mqtt/payload_schema.py`): agregado `schema_version` (default 1, valores no soportados se rechazan) y `reading_id` (opcional, compatibilidad con firmware desplegado).
- `ThermalReadingModel`: columnas `reading_id`, `schema_version` nuevas.
- `reading_id`/`schema_version` se propagan de punta a punta: payload → `LecturaTermica` → persistencia → respuesta API (`LecturaResponse`) → payload del acuse lógico (HU-07).
- Migración `0007_51hu_fase1_nucleo`.

## HU-07 — Sincronización de buffer offline con acuse lógico

- Nuevo mecanismo de ack de aplicación: `_publicar_ack_lectura()` en `src/interface/main.py` publica en `farmacias/{device_id}/ack` (QoS 1) **después** de `session.commit()`, nunca antes ni en su lugar.
- `mqtt_client.MensajeHandler` ahora recibe también el cliente activo (`Callable[[Client, Message], Awaitable[None]]`), necesario para poder publicar de vuelta.
- El acuse se publica tanto en el camino de "lectura nueva" como en el de "duplicado detectado" (reenvío tras un ack perdido).
- **Hallazgo al implementar el lado firmware:** los rechazos PERMANENTES (`DispositivoNoAutorizadoError`, `LecturaInvalidaError` — timestamp implausible, B-10) no publicaban ningún acuse. El firmware, al implementar HU-07 esperando este ack para liberar el bloque de LittleFS, habría reintentado esa lectura para siempre y bloqueado toda la cola FIFO detrás de ella (`core::drenar` se detiene en el primer fallo de publicación). `_publicar_ack_lectura()` ahora acepta un parámetro `estado` (`"commit_confirmado"` por defecto); ambas ramas de rechazo lo llaman con `"dispositivo_no_autorizado"` / `"lectura_invalida"` — el firmware no necesita interpretar el motivo, solo dejar de reintentar al recibir cualquier acuse para su `reading_id`. Cubierto por `test_dispositivo_no_autorizado_tambien_recibe_ack` y `test_lectura_invalida_tambien_recibe_ack`.
- El firmware (ESP32) ahora sí se suscribe a este tópico y espera el ack antes de borrar el bloque de LittleFS — ver `iot-firmware/CAMBIOS_AUDITORIA_51HU.md`.

## HU-17 — Evolución térmica sin imputación de valores neutros

- `clasificar_riesgo_termico.py`: eliminado `HUMEDAD_FALLBACK_NEUTRA_PCT = 50.0`. La humedad ausente ahora usa el mismo fallback documentado que la temperatura ambiental (último valor válido del historial) y, si no hay historial, la lectura queda `no_clasificable` — nunca se inventa un valor.
- Nuevo guard: si hay menos de 2 lecturas previas válidas (`MINIMO_HISTORIAL_PARA_TENDENCIA`), la lectura se marca `no_clasificable` (`motivo_no_inferencia="historial_insuficiente_para_tendencia"`) en vez de calcular una tendencia con datos insuficientes.
- Efecto colateral esperado y correcto: la primera lectura de cualquier dispositivo nuevo ya no se clasifica por IA — pero **sí** puede seguir marcando excursión crítica vía la regla directa (HU-21), que es independiente de esto.

## HU-18 / HU-21 / HU-34 — model_class, effective_risk y excursion_confirmed como conceptos distintos

- `LecturaTermica`: `nivel_riesgo` (ya existente) sigue siendo el **model_class** crudo. Se agregan `excursion_confirmada: bool` y `riesgo_efectivo: NivelRiesgo | None`, calculados en `registrar_lectura_termica.py` con dos métodos nuevos en la entidad:
  - `es_excursion_confirmada()`: regla directa e inmediata — `temperatura_interna` fuera de \[2, 8\] °C, sin duración mínima ni dependencia de la IA.
  - `calcular_riesgo_efectivo()`: si hay excursión confirmada, `EXCURSION_CRITICA` siempre (aunque `nivel_riesgo` sea `None` por no_clasificable); si no, es el `nivel_riesgo` tal cual.
- La generación de alertas (`GenerarAlertaUseCase`) y los eventos SSE de episodio ahora se disparan por `riesgo_efectivo`, no por `nivel_riesgo` — así una excursión real se alerta aunque la IA no haya podido clasificar.
- `ThermalReadingModel`: columnas `excursion_confirmada`, `riesgo_efectivo` nuevas. Expuestas en `LecturaResponse`.
- Migración `0007_51hu_fase1_nucleo`.

## HU-41 — Rol AUDITOR

- `Rol` (enum): agregado `AUDITOR`, junto a `ADMINISTRADOR/FARMACEUTICO/TECNICO`.
- Acceso de lectura otorgado a `AUDITOR` en: `/api/trazabilidad`, `/api/auditoria`, `/api/lecturas` (historial), `/api/reportes/bpa`, `/api/ia/modelo`.
- Nuevo caso de uso `CambiarRolUsuarioUseCase` + endpoint `PATCH /api/usuarios/{id}/rol` (antes no existía forma de cambiar el rol de un usuario tras el alta).
- Migración `0007_51hu_fase1_nucleo` siembra la fila `auditor` en `roles`.

## HU-42 — Bitácora auditable encadenada a la cadena global

- `AuditarAccionCriticaUseCase` ahora acepta un `ITrazabilidadRepository` opcional y, cuando se provee, encadena cada entrada de `audit_logs` también en `traceability_records` (tipo de evento `AUDIT_LOG`) — ya no es una tabla paralela sin hash.
- Los 14 puntos de la API que construían `AuditarAccionCriticaUseCase` se actualizaron para pasar el repositorio de trazabilidad.

## HU-23 — Máquina de estados de alertas críticas

- Nuevo value object `EstadoAlerta` (`PENDIENTE | RECONOCIDA | ATENDIDA`).
- `AlertaTermica`: nuevos campos `estado`, `reconocida_en`, `atendida_en`; métodos `reconocer()` (rechaza si no está `PENDIENTE`) y `marcar_atendida()`.
- `PATCH /api/alertas/{id}/revisar` ahora aplica la máquina de estados completa (antes solo marcaba un booleano `revisada`).
- `POST /api/alertas/{id}/acciones-correctivas` transiciona la alerta a `ATENDIDA`.
- Migración `0008_51hu_hu23_hu27_hu28`.

## HU-27 / HU-28 — Concurrencia en acción correctiva y rectificaciones

- Nuevo método atómico `IAlertaRepository.marcar_atendida_si_no_atendida()` — un `UPDATE ... WHERE estado != 'atendida'` de una sola sentencia, no un patrón leer-modificar-escribir. `RegistrarAccionCorrectivaUseCase` lo usa **antes** de crear la acción: si pierde la carrera, devuelve 409 y no registra nada.
- Nuevo `AccionCorrectiva.corrige_accion_id` + `CorregirAccionCorrectivaUseCase` + `POST /api/alertas/acciones-correctivas/{id}/rectificar`: crea un evento nuevo que referencia al anterior, nunca sobrescribe.
- Migración `0008_51hu_hu23_hu27_hu28`.

## HU-37 — Verificación de integridad por dispositivo y periodo

- Nuevo `VerificarIntegridadPorDispositivoYPeriodoUseCase`: identifica el segmento temporal en la cadena **global** (por orden de inserción, no de `timestamp`), ancla en el registro inmediatamente anterior, verifica secuencialmente **todos** los bloques del intervalo (no solo los del dispositivo consultado) y filtra la presentación al dispositivo pedido.
- `GET /api/trazabilidad/verificar-dispositivo?device_id=&desde=&hasta=` (nuevo endpoint; `/verificar` global se conserva sin cambios).
- Registra un evento `VERIFICACION_INTEGRIDAD` append-only por cada verificación.
- Limitación documentada en el propio código: si una lectura llega muy tarde por buffer offline, el segmento puede ser más ancho que el rango pedido, nunca más angosto.

## HU-44 / HU-10 — Credencial MQTT por dispositivo, rotación y revocación

- `DeviceModel`: `mqtt_token_hash` (nunca en claro — mismo hasher que las contraseñas de usuario), `mqtt_token_activo`, `mqtt_credencial_actualizada_en`.
- `RotarCredencialDispositivoUseCase` / `RevocarCredencialDispositivoUseCase` / `VerificarCredencialDispositivoUseCase`.
- Endpoints: `POST /api/dispositivos/{id}/credenciales/rotar` (admin, devuelve el token en claro **una sola vez**), `POST /api/dispositivos/{id}/credenciales/revocar` (admin), `POST /api/dispositivos/autenticar` (sin JWT — pensado como backend de autenticación HTTP para EMQX Cloud).
- Migración `0009_51hu_hu44_hu10_credenciales`.
- **Nota real:** el cliente MQTT del propio backend sigue usando una credencial compartida (`backend_service`) para su conexión de servicio — eso es una identidad de servicio, distinta del mecanismo de credencial-por-dispositivo que este cambio entrega. La aplicación real de ACL por-dispositivo en el broker depende de configurar EMQX Cloud para llamar a `/api/dispositivos/autenticar`.

## HU-46 / HU-47 — Gobierno del modelo IA y auditoría de inferencia

- Nueva tabla `ai_model_versions` (hash SHA-256, `feature_schema_version`, `dataset_version`, versión de scikit-learn/Python, `trained_at`, quién aprobó, historial de activación).
- `RegistrarVersionModeloUseCase` / `ActivarVersionModeloUseCase`: activar una versión no registrada se rechaza (404); registrar no activa automáticamente.
- Endpoints: `POST /api/ia/modelo/versiones`, `GET /api/ia/modelo/versiones`, `POST /api/ia/modelo/versiones/{version}/activar` (todos admin, salvo el GET que también permite `AUDITOR`).
- `ResultadoInferencia` (random_forest_service.py) ahora incluye `probabilidades_por_clase` (todas las clases, no solo la ganadora) y `vector_features` — se persisten en `thermal_readings.probabilidades_ia` / `.vector_features_ia`.
- `GET /api/ia/inferencia/{lectura_id}` (HU-47): vista de solo lectura con versión del modelo, vector de features, probabilidades por clase, clasificación final, y si esa versión era la activa/aprobada en el momento de la inferencia (reconstruido desde el historial de activación).
- Migración `0010_51hu_hu46_hu47_gobierno_ia`.

## HU-43 — Ciclo de vida de dispositivos IoT (alta explícita)

- `POST /api/dispositivos` (nuevo, admin): alta con `device_id`, nombre, ubicación, sensores habilitados. Rechaza `device_id` ya usado, **incluso si el dispositivo fue dado de baja** (`existio_alguna_vez()`).
- Antes los dispositivos solo se autocreaban implícitamente al llegar su primera lectura MQTT, sin metadata ni control de reutilización de identidad.

## HU-49 — Historial auditable de configuración del hardware

- Nueva tabla `device_config_history` (campo, valor anterior, valor nuevo, actor, timestamp).
- Se registra automáticamente en: cambio de ubicación (HU-51) y registro de calibración (HU-30, `RegistrarCalibracionUseCase` actualizado).
- `GET /api/dispositivos/{id}/historial-configuracion` (admin/auditor, solo lectura).
- Migración `0011_51hu_hu43_hu49_hu51_dispositivos`.

## HU-51 — Ubicación y metadatos de instalación del sensor

- `DeviceModel`: `fecha_instalacion`, `instalado_por`, `observaciones_instalacion`.
- `PATCH /api/dispositivos/{id}/instalacion` (admin): actualiza ubicación + metadata; un cambio de ubicación genera un evento en `device_config_history` (HU-49) en vez de sobrescribir en silencio.
- Migración `0011_51hu_hu43_hu49_hu51_dispositivos`.

## HU-15 — Validación de telemetría entrante (estado por sensor)

- `LecturaPayload`: nuevos campos opcionales `estado_temperatura_interna`, `estado_temperatura_ambiental`, `estado_humedad_ambiental` (`"ok" | "sensor_error" | "fuera_de_rango"`).
- Validador conjunto: si el firmware los envía, un valor `null` debe venir con un estado ≠ `"ok"`, y un valor presente debe venir con estado `"ok"` (o sin declarar, por compatibilidad).

## HU-20 — Ventana de normalización configurable

- Nuevo `Settings.alerta_ventana_normalizacion_minutos` (default 15, igual que antes pero ahora configurable por entorno).
- `GenerarAlertaUseCase` acepta `ventana_normalizacion_minutos` en el constructor; ambos puntos de construcción (`main.py`, `lecturas_router.py`) lo pasan desde `Settings`.

## HU-36 — Validación de rango invertido en el historial (server-side)

- `GET /api/lecturas`: rechaza `desde > hasta` con 422 en el propio backend, no solo en el frontend.

## HU-39 — Argon2id

- `password_hasher.py`: esquema por defecto pasa de bcrypt a Argon2id (`CryptContext(schemes=["argon2", "bcrypt"], deprecated=["bcrypt"])`). bcrypt se mantiene únicamente para seguir verificando hashes ya existentes — ningún usuario queda con su contraseña invalidada.
- Nueva dependencia `argon2-cffi` en `requirements.txt`.

## HU-50 — Supervisión de eventos de seguridad

- `IAuditLogRepository.listar()` / `GET /api/auditoria`: nuevos filtros `desde`, `hasta`, `usuario_id`, `accion`.
- Nuevo evento administrativo distinto por cada intento individual: `UMBRAL_INTENTOS_FALLIDOS_EXCEDIDO`, registrado en `auth_router.py` cuando el limitador de login bloquea un intento — antes ese caso ni siquiera se auditaba.

## HU-04 — Dispositivo sin sensor MC-38 (puerta)

- Contrato de payload (`LecturaPayload`) y entidad (`LecturaTermica`): `apertura_refrigerador` pasa de `bool` a `bool | None`. `None` significa "este nodo no tiene MC-38 instalado", no "puerta cerrada" — antes un nodo sin ese sensor no tenía forma de declarar "no aplica" sin simular una puerta que en realidad no existe. Nuevo campo opcional `mc38_status: "ok" | "not_installed"` en el payload (informativo; no se persiste aparte porque `apertura_refrigerador IS NULL` ya es la señal completa).
- `ThermalReadingModel.apertura_refrigerador`: columna relajada a NULLABLE.
- `ClasificarRiesgoTermicoUseCase._construir_features`: cuando `apertura_refrigerador` es `None`, se pasa `False` al vector de features de la IA — es un hecho de configuración de hardware, no un dato faltante, así que un neutro no "afecta la IA" (criterio explícito de HU-04). `FeaturesRiesgoTermico.apertura_refrigerador` se mantiene `bool` no-opcional a propósito: el punto donde se decide qué significa la ausencia es este único lugar, no cada consumidor del vector.
- `LecturaResponse.apertura_refrigerador`: `bool | None`.
- `generador_pdf.py`: nueva columna de reporte distingue "Abierta" / "Cerrada" / "N/D (sin MC-38)" en vez de tratar `None` como `False` (mostraría "Cerrada" para un sensor que no existe).
- Migración `0012_hu04_mc38_ausente`: `ALTER COLUMN apertura_refrigerador DROP NOT NULL` (vía `batch_alter_table`, patrón SQLite-safe ya usado en el resto de migraciones de este backlog).
- Corresponde a la mitad del contrato del firmware: ver `iot-firmware/CAMBIOS_AUDITORIA_51HU.md` para `PayloadCore`/`PayloadBuilder`.
- Efecto colateral: `test_migraciones.py::_esquema_completo` comparaba solo nombres de columna, así que un round-trip que únicamente cambia `nullable` (como esta migración) era invisible para `test_downgrade_deshace_la_ultima_migracion`. Se corrigió para comparar pares `(nombre, nullable)`, sin volver a atarse a nombres de columna de una migración específica.

## HU-35 — Notificación UI de puerta abierta (evidencia expuesta)

- **Hallazgo:** el firmware ya reporta `duracion_apertura_segundos` en cada payload (HU-04) y el backend ya lo guardaba en la columna JSONB `payload` (`evidencia_edge()`), pero `LecturaResponse` nunca lo exponía — ni por REST ni por SSE. El frontend no tenía forma de saber cuánto llevaba una puerta abierta para avisar del umbral (criterio 2 de HU-35); solo veía `apertura_refrigerador: true/false`, sin duración.
- `LecturaResponse.duracion_apertura_segundos: int | None` (nuevo). `mappers.py`: nueva `_duracion_apertura(payload)` extrae el campo del JSONB con tipo verificado (nunca confía en que el JSONB tenga la forma esperada). Fluye automáticamente al evento SSE porque `main.py` reusa `lectura_to_response(...).model_dump()` para ambos caminos.
- No requiere migración: el dato ya estaba persistido, solo faltaba exponerlo.
- Prueba nueva: `test_duracion_apertura_llega_al_evento_sse`.
- El resto de HU-35 (umbral configurable, resaltado visual, desaparición al cerrar la puerta) es UI pura — ver `frontend/CAMBIOS_AUDITORIA_51HU.md`.

## HU-29 — Respaldo y restauración

- **Sin cambio de código.** Confirmado en esta pasada: la configuración de respaldo (Railway) y las pruebas de restauración son responsabilidad operativa/infraestructura, fuera del alcance de este repositorio. No se simuló un mecanismo de "fallo de backup → alerta" porque no hay ningún job de backup real que este código controle — hacerlo habría sido decoración, no una implementación real.

---

## Migraciones nuevas

| Revisión | Contenido |
|---|---|
| `0007_51hu_fase1_nucleo` | HU-05, HU-18/21/34, HU-41 |
| `0008_51hu_hu23_hu27_hu28` | HU-23, HU-27/28 |
| `0009_51hu_hu44_hu10_credenciales` | HU-44/HU-10 |
| `0010_51hu_hu46_hu47_gobierno_ia` | HU-46/HU-47 |
| `0011_51hu_hu43_hu49_hu51_dispositivos` | HU-43, HU-49, HU-51 |
| `0012_hu04_mc38_ausente` | HU-04 |

Todas probadas con upgrade/downgrade/re-upgrade round-trip (`test_migraciones.py`, ahora genérico — compara el esquema completo en vez de nombres de columna de "la última migración", así no hay que reescribirlo cada vez que se agrega una).

## Archivos de test nuevos

- `test_hu05_hu07_payload_y_ack.py`
- `test_hu41_rol_auditor.py`
- `test_hu23_hu27_hu28_alertas.py`
- `test_hu37_verificacion_por_dispositivo.py`
- `test_hu44_hu10_credenciales_dispositivo.py`
- `test_hu46_hu47_gobierno_ia.py`
- `test_fase3_pulido_51hu.py`

## Lo que NO se tocó (fuera de alcance de este repositorio)

- El cliente MQTT propio del backend sigue con credencial compartida (identidad de servicio, no de dispositivo — ver nota en HU-44).
- La aplicación real de ACL por-dispositivo en el broker requiere configurar EMQX Cloud para usar `/api/dispositivos/autenticar` como backend de autenticación HTTP; este repositorio expone el endpoint pero no puede configurar EMQX Cloud por sí mismo.
- HU-06/HU-08/HU-13 (firmware): ver `iot-firmware/CAMBIOS_AUDITORIA_51HU.md`.
