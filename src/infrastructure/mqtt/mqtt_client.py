import asyncio
import contextlib
import ssl
from collections.abc import AsyncIterator, Awaitable, Callable

import aiomqtt

from src.infrastructure.config import Settings

TOPIC_LECTURAS = "farmacias/+/lecturas"
TOPIC_EVENTOS = "farmacias/+/eventos"

MensajeHandler = Callable[[aiomqtt.Message], Awaitable[None]]


def build_ssl_context(tls_enabled: bool) -> ssl.SSLContext | None:
    return ssl.create_default_context() if tls_enabled else None


def build_client(settings: Settings) -> aiomqtt.Client:
    return aiomqtt.Client(
        hostname=settings.mqtt_host,
        port=settings.mqtt_port,
        username=settings.mqtt_username,
        password=settings.mqtt_password.encode(),
        identifier=settings.mqtt_client_id,
        ssl_context=build_ssl_context(settings.mqtt_tls_enabled),
        reconnect=True,
        keep_alive=60,
    )


async def consumir_mensajes(client: aiomqtt.Client, manejador: MensajeHandler) -> None:
    async for message in client.messages():
        try:
            await manejador(message)
        except Exception:
            # No se propaga: un mensaje malformado no debe tumbar el consumidor MQTT.
            continue


@contextlib.asynccontextmanager
async def mqtt_session(settings: Settings, manejador: MensajeHandler) -> AsyncIterator[aiomqtt.Client]:
    """Context manager reutilizable en el lifespan de FastAPI (ver README sección 5)."""
    async with build_client(settings) as client:
        await client.subscribe(TOPIC_LECTURAS)
        await client.subscribe(TOPIC_EVENTOS)
        task = asyncio.create_task(consumir_mensajes(client, manejador))
        try:
            yield client
        finally:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
