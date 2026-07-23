import contextlib
import logging
from collections.abc import AsyncIterator
from datetime import datetime, timezone

import aiomqtt
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware

from src.application.use_cases.auditar_accion_critica import AuditarAccionCriticaUseCase
from src.application.use_cases.clasificar_riesgo_termico import ClasificarRiesgoTermicoUseCase
from src.application.use_cases.registrar_lectura_termica import RegistrarLecturaTermicaUseCase
from src.domain.entities.lectura_termica import LecturaTermica
from src.domain.exceptions import DispositivoNoAutorizadoError, LecturaInvalidaError
from src.infrastructure.ai.random_forest_service import get_random_forest_service
from src.infrastructure.config import get_settings
from src.infrastructure.database.repositories.alerta_repository import SQLAlchemyAlertaRepository
from src.infrastructure.database.repositories.audit_log_repository import (
    SQLAlchemyAuditLogRepository,
)
from src.infrastructure.database.repositories.device_repository import SQLAlchemyDeviceRepository
from src.infrastructure.database.repositories.lectura_repository import SQLAlchemyLecturaRepository
from src.infrastructure.database.repositories.trazabilidad_repository import (
    SQLAlchemyTrazabilidadRepository,
)
from src.infrastructure.database.session import _session_factory
from src.infrastructure.mqtt.mqtt_client import mqtt_session
from src.infrastructure.mqtt.payload_schema import LecturaPayload
from src.infrastructure.security.rate_limiter import SlidingWindowRateLimiter
from src.infrastructure.security.revocation_store import JtiStore
from src.interface.api.api_protection import instalar_proteccion_api
from src.interface.api.alertas_router import router as alertas_router
from src.interface.api.auditoria_router import router as auditoria_router
from src.interface.api.auth_router import router as auth_router
from src.interface.api.dispositivos_router import router as dispositivos_router
from src.interface.api.firmware_router import router as firmware_router
from src.interface.api.ia_router import router as ia_router
from src.interface.api.lecturas_router import router as lecturas_router
from src.interface.api.mappers import lectura_to_response
from src.interface.api.reportes_router import router as reportes_router
from src.interface.api.sse_broadcaster import SSEBroadcaster
from src.interface.api.security_headers import instalar_security_headers
from src.interface.api.sse_router import router as sse_router
from src.interface.api.trazabilidad_router import router as trazabilidad_router
from src.interface.api.usuarios_router import router as usuarios_router

logger = logging.getLogger("interface.main")


def _device_id_del_topic(topic: str) -> str | None:
    """En `farmacias/{device_id}/lecturas` el segmento intermedio identifica
    al dispositivo autenticado ante el broker."""
    partes = topic.split("/")
    if len(partes) != 3 or partes[0] != "farmacias" or partes[2] != "lecturas":
        return None
    return partes[1] or None


async def _procesar_mensaje_mqtt(message: aiomqtt.Message, broadcaster: SSEBroadcaster) -> None:
    payload = LecturaPayload.model_validate_json(message.payload)
    settings = get_settings()

    # Anti-suplantación: el device_id declarado en el payload debe coincidir
    # con el segmento del tópico sobre el que el broker autorizó publicar.
    device_topic = _device_id_del_topic(str(message.topic))
    if device_topic is None or device_topic != payload.device_id:
        logger.warning(
            "Descartado: tópico MQTT inválido o device_id (%s) no coincide con el tópico (%s)",
            payload.device_id,
            device_topic,
        )
        return

    async with _session_factory() as session:
        lectura_repository = SQLAlchemyLecturaRepository(session)
        alerta_repository = SQLAlchemyAlertaRepository(session)
        trazabilidad_repository = SQLAlchemyTrazabilidadRepository(session)
        clasificar_use_case = ClasificarRiesgoTermicoUseCase(get_random_forest_service())
        use_case = RegistrarLecturaTermicaUseCase(
            lectura_repository,
            alerta_repository,
            trazabilidad_repository,
            clasificar_use_case,
            device_repository=SQLAlchemyDeviceRepository(session),
            registro_dispositivos_estricto=settings.device_registry_estricto,
        )

        lectura = LecturaTermica(
            device_id=payload.device_id,
            timestamp=payload.timestamp,
            temperatura_ambiental=payload.temperatura_ambiental,
            humedad_ambiental=payload.humedad_ambiental,
            temperatura_interna=payload.temperatura_interna,
            apertura_refrigerador=payload.apertura_refrigerador,
            estado_conectividad=payload.estado_conectividad,
        )
        # Reenvío QoS1: no publicar un segundo SSE lógico. El caso de uso
        # conserva misma garantía en BD; este guard evita notificación doble.
        existente = await lectura_repository.obtener_por_device_y_timestamp(
            payload.device_id, payload.timestamp
        )
        if existente is not None:
            logger.info("Lectura MQTT duplicada omitida: %s/%s", payload.device_id, payload.timestamp)
            return

        episodio_previo = await alerta_repository.obtener_episodio_abierto(payload.device_id)
        try:
            lectura_guardada = await use_case.execute(lectura)
        except DispositivoNoAutorizadoError:
            auditoria = AuditarAccionCriticaUseCase(SQLAlchemyAuditLogRepository(session))
            await auditoria.execute(
                usuario_id=None,
                accion="DISPOSITIVO_RECHAZADO",
                recurso="mqtt/lecturas",
                detalle={"device_id": payload.device_id},
                ip_origen=None,
            )
            await session.commit()
            logger.warning("Dispositivo no registrado rechazado: %s", payload.device_id)
            return
        except LecturaInvalidaError:
            logger.warning("Lectura inválida descartada para device %s", payload.device_id)
            return
        episodio_actual = await alerta_repository.obtener_episodio_abierto(payload.device_id)
        await session.commit()

    evento_lectura = lectura_to_response(lectura_guardada).model_dump(mode="json")
    if lectura_guardada.estado_inferencia == "omitida":
        tipo = "fallo_sensor" if lectura_guardada.origen_clasificacion == "fallo_sensor" else "inferencia_omitida"
    else:
        tipo = "lectura"
    await broadcaster.publicar(evento_lectura, tipo)

    if lectura_guardada.nivel_riesgo is not None and episodio_previo is not None and episodio_actual is None:
        await broadcaster.publicar(evento_lectura, "recuperacion")
    elif lectura_guardada.nivel_riesgo is not None and episodio_actual is not None:
        tipo_episodio = "alerta" if episodio_previo is None else "episodio_actualizado"
        await broadcaster.publicar(
            {
                **evento_lectura,
                "episodio_alerta": str(episodio_actual.id),
                "alerta_abierta": episodio_actual.episodio_abierto,
                "lectura_inicial_id": str(episodio_actual.lectura_inicial_id),
                "lectura_mas_reciente_id": str(episodio_actual.lectura_mas_reciente_id),
            },
            tipo_episodio,
        )


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    app.state.sse_broadcaster = SSEBroadcaster()

    if settings.mqtt_enabled and settings.environment != "test":

        async def manejador(message: aiomqtt.Message) -> None:
            await _procesar_mensaje_mqtt(message, app.state.sse_broadcaster)

        try:
            async with mqtt_session(settings, manejador) as client:
                app.state.mqtt = client
                yield
        except aiomqtt.MqttError as exc:
            logger.warning("No se pudo conectar a EMQX Cloud Serverless: %s. Backend continúa sin MQTT.", exc)
            app.state.mqtt = None
            yield
    else:
        app.state.mqtt = None
        yield


def create_app() -> FastAPI:
    settings = get_settings()
    es_produccion = settings.environment == "production"

    app = FastAPI(
        title="IoT Cadena de Frío Farmacéutica - Backend",
        description=(
            "Prototipo IoT + IA con trazabilidad digital verificable para el monitoreo "
            "de la cadena de frío de medicamentos termolábiles en farmacias independientes."
        ),
        version="1.0.0",
        lifespan=lifespan,
        # La documentación interactiva no se expone en producción.
        docs_url=None if es_produccion else "/docs",
        redoc_url=None if es_produccion else "/redoc",
        openapi_url=None if es_produccion else "/openapi.json",
    )

    app.state.login_rate_limiter = SlidingWindowRateLimiter(
        max_intentos=settings.login_max_intentos,
        ventana_segundos=settings.login_ventana_segundos,
        max_claves=settings.security_state_max_entries,
    )
    # Revocación de access tokens (logout) y consumo único de tickets SSE.
    app.state.token_revocation = JtiStore(settings.security_state_max_entries)
    app.state.sse_ticket_store = JtiStore(settings.security_state_max_entries)

    if es_produccion:
        app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
    )
    instalar_security_headers(app, hsts=es_produccion)
    instalar_proteccion_api(app, settings)

    app.include_router(auth_router)
    app.include_router(usuarios_router)
    app.include_router(lecturas_router)
    app.include_router(alertas_router)
    app.include_router(trazabilidad_router)
    app.include_router(reportes_router)
    app.include_router(auditoria_router)
    app.include_router(ia_router)
    app.include_router(sse_router)
    app.include_router(dispositivos_router)
    app.include_router(firmware_router)

    @app.get("/health", tags=["health"])
    async def health() -> dict:
        return {"status": "ok", "timestamp": datetime.now(tz=timezone.utc).isoformat()}

    return app


app = create_app()
