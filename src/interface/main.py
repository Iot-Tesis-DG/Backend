import contextlib
import logging
from collections.abc import AsyncIterator
from datetime import datetime, timezone

import aiomqtt
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.application.use_cases.clasificar_riesgo_termico import ClasificarRiesgoTermicoUseCase
from src.application.use_cases.registrar_lectura_termica import RegistrarLecturaTermicaUseCase
from src.domain.entities.lectura_termica import LecturaTermica
from src.domain.exceptions import LecturaInvalidaError
from src.infrastructure.ai.random_forest_service import get_random_forest_service
from src.infrastructure.config import get_settings
from src.infrastructure.database.repositories.alerta_repository import SQLAlchemyAlertaRepository
from src.infrastructure.database.repositories.lectura_repository import SQLAlchemyLecturaRepository
from src.infrastructure.database.repositories.trazabilidad_repository import (
    SQLAlchemyTrazabilidadRepository,
)
from src.infrastructure.database.session import _session_factory
from src.infrastructure.mqtt.mqtt_client import mqtt_session
from src.infrastructure.mqtt.payload_schema import LecturaPayload
from src.interface.api.alertas_router import router as alertas_router
from src.interface.api.auditoria_router import router as auditoria_router
from src.interface.api.auth_router import router as auth_router
from src.interface.api.lecturas_router import router as lecturas_router
from src.interface.api.mappers import lectura_to_response
from src.interface.api.reportes_router import router as reportes_router
from src.interface.api.sse_broadcaster import SSEBroadcaster
from src.interface.api.sse_router import router as sse_router
from src.interface.api.trazabilidad_router import router as trazabilidad_router
from src.interface.api.usuarios_router import router as usuarios_router

logger = logging.getLogger("interface.main")


async def _procesar_mensaje_mqtt(message: aiomqtt.Message, broadcaster: SSEBroadcaster) -> None:
    payload = LecturaPayload.model_validate_json(message.payload)

    async with _session_factory() as session:
        lectura_repository = SQLAlchemyLecturaRepository(session)
        alerta_repository = SQLAlchemyAlertaRepository(session)
        trazabilidad_repository = SQLAlchemyTrazabilidadRepository(session)
        clasificar_use_case = ClasificarRiesgoTermicoUseCase(get_random_forest_service())
        use_case = RegistrarLecturaTermicaUseCase(
            lectura_repository, alerta_repository, trazabilidad_repository, clasificar_use_case
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
        try:
            lectura_guardada = await use_case.execute(lectura)
        except LecturaInvalidaError:
            logger.warning("Lectura inválida descartada para device %s", payload.device_id)
            return
        await session.commit()

    await broadcaster.publicar(lectura_to_response(lectura_guardada).model_dump(mode="json"))


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
    app = FastAPI(
        title="IoT Cadena de Frío Farmacéutica - Backend",
        description=(
            "Prototipo IoT + IA con trazabilidad digital verificable para el monitoreo "
            "de la cadena de frío de medicamentos termolábiles en farmacias independientes."
        ),
        version="1.0.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(auth_router)
    app.include_router(usuarios_router)
    app.include_router(lecturas_router)
    app.include_router(alertas_router)
    app.include_router(trazabilidad_router)
    app.include_router(reportes_router)
    app.include_router(auditoria_router)
    app.include_router(sse_router)

    @app.get("/health", tags=["health"])
    async def health() -> dict:
        return {"status": "ok", "timestamp": datetime.now(tz=timezone.utc).isoformat()}

    return app


app = create_app()
