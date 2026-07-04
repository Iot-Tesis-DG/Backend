from datetime import datetime

from pydantic import BaseModel, Field


class LecturaPayload(BaseModel):
    """Valida el payload JSON publicado por el firmware ESP32 (ver README sección 3)."""

    device_id: str = Field(min_length=1, max_length=50)
    timestamp: datetime
    temperatura_ambiental: float | None = Field(default=None, ge=-40.0, le=125.0)
    humedad_ambiental: float | None = Field(default=None, ge=0.0, le=100.0)
    temperatura_interna: float | None = Field(default=None, ge=-55.0, le=125.0)
    apertura_refrigerador: bool = False
    estado_conectividad: str = "online"
    firmware_version: str | None = None
