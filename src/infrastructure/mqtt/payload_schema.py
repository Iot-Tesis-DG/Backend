from datetime import datetime

from pydantic import AliasChoices, BaseModel, ConfigDict, Field


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
    estado_conectividad: str = "online"
    firmware_version: str | None = None
