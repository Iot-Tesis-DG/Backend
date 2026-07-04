from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from src.domain.value_objects.nivel_riesgo import NivelRiesgo
from src.domain.value_objects.rol import Rol


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UsuarioCreateRequest(BaseModel):
    nombre: str = Field(min_length=1, max_length=120)
    email: EmailStr
    password: str = Field(min_length=8)
    rol: Rol


class UsuarioResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    nombre: str
    email: str
    rol: Rol


class LecturaIngestRequest(BaseModel):
    """Espejo de src.infrastructure.mqtt.payload_schema.LecturaPayload para ingesta vía REST."""

    device_id: str = Field(min_length=1, max_length=50)
    timestamp: datetime
    temperatura_ambiental: float | None = Field(default=None, ge=-40.0, le=125.0)
    humedad_ambiental: float | None = Field(default=None, ge=0.0, le=100.0)
    temperatura_interna: float | None = Field(default=None, ge=-55.0, le=125.0)
    apertura_refrigerador: bool = False
    estado_conectividad: str = "online"


class LecturaResponse(BaseModel):
    id: UUID | None = None
    device_id: str
    timestamp: datetime
    temperatura_ambiental: float | None
    humedad_ambiental: float | None
    temperatura_interna: float | None
    apertura_refrigerador: bool
    estado_conectividad: str
    nivel_riesgo: NivelRiesgo | None


class AlertaResponse(BaseModel):
    id: UUID | None = None
    reading_id: UUID
    device_id: str
    nivel_riesgo: NivelRiesgo
    mensaje: str
    revisada: bool
    revisada_por: UUID | None = None
    created_at: datetime | None = None


class AccionCorrectivaCreateRequest(BaseModel):
    descripcion: str = Field(min_length=1, max_length=2000)


class AccionCorrectivaResponse(BaseModel):
    id: UUID | None = None
    alert_id: UUID
    usuario_id: UUID
    descripcion: str
    created_at: datetime | None = None


class TrazabilidadResponse(BaseModel):
    id: UUID | None = None
    tipo_evento: str
    device_id: str | None
    usuario_id: UUID | None
    payload: dict
    timestamp: datetime
    previous_hash: str
    hash_actual: str


class VerificacionIntegridadResponse(BaseModel):
    integra: bool
    total_registros: int
    primer_registro_inconsistente: int | None


class ReporteBPAResponse(BaseModel):
    device_id: str | None
    fecha_desde: datetime
    fecha_hasta: datetime
    lecturas: list[LecturaResponse]
    alertas: list[AlertaResponse]
    registros_trazabilidad: list[TrazabilidadResponse]


class AuditLogResponse(BaseModel):
    id: UUID
    usuario_id: UUID | None
    accion: str
    recurso: str
    detalle: dict | None
    ip_origen: str | None
    created_at: datetime
