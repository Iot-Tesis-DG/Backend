from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from src.domain.value_objects.nivel_riesgo import NivelRiesgo
from src.domain.value_objects.rol import Rol

PASSWORD_MIN_LENGTH = 10


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    require_privacy_consent: bool = False


class SSETicketResponse(BaseModel):
    ticket: str


class PrivacidadResponse(BaseModel):
    privacy_accepted: bool
    privacy_version_accepted: str | None


class UsuarioCreateRequest(BaseModel):
    nombre: str = Field(min_length=1, max_length=120)
    email: EmailStr
    password: str = Field(min_length=PASSWORD_MIN_LENGTH, max_length=128)
    rol: Rol

    @field_validator("password")
    @classmethod
    def _politica_password(cls, valor: str) -> str:
        if not any(c.isdigit() for c in valor) or not any(c.isalpha() for c in valor):
            raise ValueError("La contraseña debe combinar letras y números")
        return valor


class UsuarioResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    nombre: str
    email: str
    rol: Rol
    is_active: bool = True
    motivo_desactivacion: str | None = None
    desactivado_en: datetime | None = None


class DesactivarUsuarioRequest(BaseModel):
    motivo: str = Field(min_length=1, max_length=50)


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
    # Evidencia de la inferencia de IA (RNF-04, corrige hallazgo AI-07 de la
    # auditoría: el contrato SSE no exponía confianza ni versión del modelo).
    confianza_ia: float | None = None
    modelo_version: str | None = None
    # Alias en inglés requerido por integración externa; se mantiene
    # `modelo_version` para no romper clientes ya desplegados.
    model_version: str | None = None
    # AIV-04 (fase de corrección): procedencia y estado real de la
    # clasificación — antes solo auditables en base de datos, no en la API.
    origen_clasificacion: str | None = None
    estado_inferencia: str | None = None
    motivo_no_inferencia: str | None = None
    estado_sensores: dict[str, str] | None = None


class AlertaResponse(BaseModel):
    id: UUID | None = None
    reading_id: UUID
    device_id: str
    nivel_riesgo: NivelRiesgo
    mensaje: str
    revisada: bool
    revisada_por: UUID | None = None
    created_at: datetime | None = None
    # AIV-02 (fase de corrección): evidencia de episodio, no de lectura aislada.
    episodio_abierto: bool = True
    lectura_inicial_id: UUID | None = None
    lectura_mas_reciente_id: UUID | None = None
    ultima_actualizacion: datetime | None = None
    cerrada_en: datetime | None = None


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


class DetalleInconsistenciaResponse(BaseModel):
    id: UUID
    tipo_evento: str
    timestamp: datetime
    hash_esperado: str
    hash_almacenado: str
    mensaje: str


class VerificacionIntegridadResponse(BaseModel):
    integra: bool
    total_registros: int
    primer_registro_inconsistente: int | None
    detalle_inconsistencia: DetalleInconsistenciaResponse | None = None
    registros_posteriores_afectados: int = 0


class EstadoCadenaResponse(BaseModel):
    cadena_comprometida: bool


class ReporteBPAResponse(BaseModel):
    device_id: str | None
    fecha_desde: datetime
    fecha_hasta: datetime
    lecturas: list[LecturaResponse]
    alertas: list[AlertaResponse]
    registros_trazabilidad: list[TrazabilidadResponse]


class DispositivoResponse(BaseModel):
    id: str
    nombre: str | None
    ubicacion: str | None
    estado_conectividad: str
    activo: bool
    firmware_version: str
    motivo_baja: str | None = None
    descripcion_baja: str | None = None
    dado_de_baja_en: datetime | None = None
    reemplaza_a_device_id: str | None = None


class DispositivoBajaRequest(BaseModel):
    motivo: str = Field(min_length=1, max_length=50)
    descripcion: str | None = Field(default=None, max_length=2000)
    device_id_reemplazo: str | None = Field(default=None, max_length=50)


class FirmwareReleaseCreateRequest(BaseModel):
    version: str = Field(min_length=1, max_length=20)
    hash_sha256: str = Field(min_length=64, max_length=64)
    descripcion: str = Field(min_length=1, max_length=2000)


class FirmwareReleaseResponse(BaseModel):
    id: UUID
    version: str
    hash_sha256: str
    descripcion: str
    fecha_compilacion: datetime


class FirmwareDespliegueCreateRequest(BaseModel):
    device_id: str = Field(min_length=1, max_length=50)
    version_objetivo: str = Field(min_length=1, max_length=20)
    programado_para: datetime | None = None


class FirmwareDespliegueResponse(BaseModel):
    id: UUID
    device_id: str
    version_objetivo: str
    estado: str
    programado_para: datetime | None
    resultado: str | None
    completado_en: datetime | None


class AuditLogResponse(BaseModel):
    id: UUID
    usuario_id: UUID | None
    accion: str
    recurso: str
    detalle: dict | None
    ip_origen: str | None
    created_at: datetime
