from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field

# Techo del cuerpo de un mensaje MQTT aceptado. `PayloadBuilder::build()` del
# firmware descarta cualquier payload de más de 512 bytes antes de publicarlo
# (ver PayloadCore.h), así que este margen es diez veces el máximo legítimo.
#
# Existe porque la ingesta MQTT no atraviesa el middleware HTTP que acota el
# cuerpo de las peticiones REST (`max_body_bytes`): sin él, quien tuviera
# credenciales del broker podía obligar al backend a materializar en memoria un
# mensaje arbitrariamente grande, en una instancia de 512 MB.
MAX_BYTES_PAYLOAD_MQTT = 5 * 1024


class LecturaPayload(BaseModel):
    """Valida el payload JSON publicado por el firmware ESP32 (ver README sección 3)."""

    # El contrato MQTT es cerrado: no se silencian campos inesperados y NaN/
    # infinito nunca llega a persistencia, IA ni trazabilidad.
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    device_id: str = Field(min_length=1, max_length=50)
    timestamp: datetime
    # Acepta contrato interno y nombres de firmware/simulador. Se serializa
    # siempre con los nombres internos, así no rompe backend existente.
    message_id: str | None = Field(default=None, max_length=100)
    temperatura_ambiental: float | None = Field(
        default=None, ge=-40.0, le=125.0,
        validation_alias=AliasChoices("temperatura_ambiental", "temperatura_sht31"),
    )
    humedad_ambiental: float | None = Field(
        default=None, ge=0.0, le=100.0,
        validation_alias=AliasChoices("humedad_ambiental", "humedad"),
    )
    temperatura_interna: float | None = Field(
        default=None, ge=-55.0, le=125.0,
        validation_alias=AliasChoices("temperatura_interna", "temperatura_ds18b20"),
    )
    apertura_refrigerador: bool = Field(
        default=False, validation_alias=AliasChoices("apertura_refrigerador", "puerta_abierta")
    )
    # El firmware solo emite estos dos valores (`lectura.online ? "online" :
    # "offline"`). Declararlo como `str` libre dejaba entrar cualquier cadena
    # hasta la columna `String(20)` de la base de datos, donde PostgreSQL la
    # rechaza con un error de escritura en vez de con un 422 en el borde.
    estado_conectividad: Literal["online", "offline"] = "online"
    # Mismo techo que `EventoDispositivoPayload.firmware_version` y que la
    # columna `devices.firmware_version`, que es String(20). Sin él, esta rama
    # del contrato admitía una cadena ilimitada que acababa en la columna JSONB
    # `payload` de cada lectura.
    firmware_version: str | None = Field(default=None, max_length=20)
    # HU-04: el nodo acompaña cada apertura de puerta con su duración
    # acumulada. `PayloadBuilder::build()` lo emite SIEMPRE (0 con la puerta
    # cerrada), así que sin este campo `extra="forbid"` rechazaba el 100% de
    # las lecturas del firmware real. Ver IoT-documentacion_iot.md §3.5.
    duracion_apertura_segundos: int = Field(default=0, ge=0)


class TipoEventoDispositivo(StrEnum):
    """B-09: eventos que el nodo publica en `farmacias/{device_id}/eventos`,
    separados del flujo de lecturas."""

    LWT_ONLINE = "lwt_online"
    LWT_OFFLINE = "lwt_offline"
    ERROR_SENSOR = "error_sensor"
    FIRMWARE_UPDATE = "firmware_update"


class EventoDispositivoPayload(BaseModel):
    """Mensaje de estado del dispositivo (incluido el Last Will and Testament
    que el broker publica cuando el ESP32 pierde la conexión sin despedirse).

    Antes de este esquema, todo mensaje del tópico `/eventos` se validaba
    contra `LecturaPayload`, fallaba y se descartaba en silencio: las
    desconexiones del nodo nunca llegaban a registrarse."""

    model_config = ConfigDict(extra="forbid")

    device_id: str = Field(min_length=1, max_length=50)
    tipo_evento: TipoEventoDispositivo
    timestamp: datetime
    detalle: str | None = Field(default=None, max_length=500)
    firmware_version: str | None = Field(default=None, max_length=20)
