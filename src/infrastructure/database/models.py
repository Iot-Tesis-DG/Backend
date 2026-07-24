import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from src.infrastructure.database.base import Base

# JSON portable: JSONB en PostgreSQL, JSON plano en otros dialectos (usado en tests con SQLite).
JSONVariant = JSON().with_variant(JSONB(), "postgresql")
# Uuid genérico: nativo en PostgreSQL, CHAR(32) portable en otros dialectos (usado en tests con SQLite).


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _created_at_column() -> Mapped[datetime]:
    """Default generado en Python (microsegundos) en vez de solo server_default:
    CURRENT_TIMESTAMP en SQLite tiene resolución de 1 segundo y rompe el orden
    estable que necesita la verificación de la cadena de hash encadenado."""
    return mapped_column(DateTime(timezone=True), default=_utcnow, server_default=func.now())


class DeviceModel(Base):
    __tablename__ = "devices"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    nombre: Mapped[str | None] = mapped_column(String(120), nullable=True)
    ubicacion: Mapped[str | None] = mapped_column(String(200), nullable=True)
    estado_conectividad: Mapped[str] = mapped_column(String(20), default="offline")
    created_at: Mapped[datetime] = _created_at_column()

    # HU-43: ciclo de vida (baja/reemplazo) sin borrar el histórico.
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    firmware_version: Mapped[str] = mapped_column(String(20), default="1.0.0")
    motivo_baja: Mapped[str | None] = mapped_column(String(50), nullable=True)
    descripcion_baja: Mapped[str | None] = mapped_column(Text, nullable=True)
    dado_de_baja_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reemplaza_a_device_id: Mapped[str | None] = mapped_column(String(50), nullable=True)

    lecturas: Mapped[list["ThermalReadingModel"]] = relationship(back_populates="device")


class RoleModel(Base):
    __tablename__ = "roles"

    id: Mapped[uuid.UUID] = _uuid_pk()
    nombre: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)

    usuarios: Mapped[list["UserModel"]] = relationship(back_populates="rol")


class UserModel(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = _uuid_pk()
    nombre: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(150), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    rol_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("roles.id"), nullable=False)

    # HU-44: consentimiento explícito de la Ley N.° 29733.
    privacy_accepted: Mapped[bool] = mapped_column(Boolean, default=True)
    privacy_accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    privacy_version_accepted: Mapped[str | None] = mapped_column(String(10), nullable=True)

    # HU-45: desactivación/anonimización (derecho al olvido) sin borrar audit_logs.
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    motivo_desactivacion: Mapped[str | None] = mapped_column(String(50), nullable=True)
    desactivado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    desactivado_por: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    anonymized_for_gdpr: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = _created_at_column()

    rol: Mapped[RoleModel] = relationship(back_populates="usuarios")


class ThermalReadingModel(Base):
    __tablename__ = "thermal_readings"
    __table_args__ = (
        # Deduplicación/idempotencia (RF-07): un reenvío MQTT (PUBACK perdido,
        # QoS1) para el mismo dispositivo y el mismo instante exacto no debe
        # producir un segundo registro. Ver hallazgo B-04 de la auditoría.
        UniqueConstraint("device_id", "timestamp", name="uq_thermal_readings_device_timestamp"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    device_id: Mapped[str] = mapped_column(String(50), ForeignKey("devices.id"), nullable=False, index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    temperatura_ambiental: Mapped[float | None] = mapped_column(Float, nullable=True)
    humedad_ambiental: Mapped[float | None] = mapped_column(Float, nullable=True)
    temperatura_interna: Mapped[float | None] = mapped_column(Float, nullable=True)
    apertura_refrigerador: Mapped[bool] = mapped_column(Boolean, default=False)
    nivel_riesgo: Mapped[str | None] = mapped_column(String(30), nullable=True)
    estado_conectividad: Mapped[str | None] = mapped_column(String(20), nullable=True)
    payload: Mapped[dict | None] = mapped_column(JSONVariant, nullable=True)
    # Trazabilidad de la inferencia (RNF-04, hallazgo AI-06 de la auditoría de
    # IA): con qué versión de modelo y con qué confianza se clasificó esta
    # lectura específica. NULL cuando no se ejecutó inferencia (ORIGEN_SIN_DATO).
    modelo_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    confianza_ia: Mapped[float | None] = mapped_column(Float, nullable=True)
    origen_clasificacion: Mapped[str | None] = mapped_column(String(30), nullable=True)
    # AIV-07 (fase de corrección): estado real de la inferencia y motivo breve
    # cuando no fue "completada". NULL en registros anteriores a esta migración.
    estado_inferencia: Mapped[str | None] = mapped_column(String(30), nullable=True)
    motivo_no_inferencia: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = _created_at_column()

    device: Mapped[DeviceModel] = relationship(back_populates="lecturas")
    alertas: Mapped[list["ThermalAlertModel"]] = relationship(
        back_populates="lectura", foreign_keys="ThermalAlertModel.reading_id"
    )


class ThermalAlertModel(Base):
    __tablename__ = "thermal_alerts"
    __table_args__ = (
        # AIV-02: garantía de "una sola alerta abierta por dispositivo y tipo
        # de riesgo" a nivel de base de datos, no solo en memoria. Un índice
        # único parcial (solo sobre filas abiertas) permite reabrir un nuevo
        # episodio del mismo tipo una vez cerrado el anterior.
        UniqueConstraint(
            "device_id", "nivel_riesgo", "episodio_abierto",
            name="uq_thermal_alerts_episodio_abierto_por_device_y_riesgo",
        ),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    reading_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("thermal_readings.id"), nullable=False)
    device_id: Mapped[str] = mapped_column(String(50), ForeignKey("devices.id"), nullable=False, index=True)
    nivel_riesgo: Mapped[str] = mapped_column(String(30), nullable=False)
    mensaje: Mapped[str] = mapped_column(Text, nullable=False)
    revisada: Mapped[bool] = mapped_column(Boolean, default=False)
    revisada_por: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    # AIV-02 — control de episodio/tormenta de alertas: mientras el episodio
    # sigue abierto, esta columna vale 1 (permitiendo que el UNIQUE la
    # detecte); al cerrarse pasa a NULL (varias alertas cerradas del mismo
    # device+riesgo pueden coexistir sin violar la restricción única).
    episodio_abierto: Mapped[int | None] = mapped_column(Integer, nullable=True, default=1)
    lectura_inicial_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("thermal_readings.id"), nullable=False)
    lectura_mas_reciente_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("thermal_readings.id"), nullable=False)
    ultima_actualizacion: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow, server_default=func.now())
    cerrada_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = _created_at_column()

    lectura: Mapped[ThermalReadingModel] = relationship(back_populates="alertas", foreign_keys=[reading_id])
    acciones_correctivas: Mapped[list["CorrectiveActionModel"]] = relationship(back_populates="alerta")


class CorrectiveActionModel(Base):
    __tablename__ = "corrective_actions"

    id: Mapped[uuid.UUID] = _uuid_pk()
    alert_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("thermal_alerts.id"), nullable=False)
    usuario_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False)
    descripcion: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = _created_at_column()

    alerta: Mapped[ThermalAlertModel] = relationship(back_populates="acciones_correctivas")


class TraceabilityRecordModel(Base):
    __tablename__ = "traceability_records"

    id: Mapped[uuid.UUID] = _uuid_pk()
    tipo_evento: Mapped[str] = mapped_column(String(50), nullable=False)
    device_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    usuario_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    payload: Mapped[dict] = mapped_column(JSONVariant, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    previous_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    hash_actual: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    created_at: Mapped[datetime] = _created_at_column()
    # HU-47: aislamiento de un registro corrupto y marca de "posterior al punto de ruptura".
    is_corrupted: Mapped[bool] = mapped_column(Boolean, default=False)
    is_after_corruption: Mapped[bool] = mapped_column(Boolean, default=False)


class AuditLogModel(Base):
    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = _uuid_pk()
    usuario_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    accion: Mapped[str] = mapped_column(String(100), nullable=False)
    recurso: Mapped[str] = mapped_column(String(100), nullable=False)
    detalle: Mapped[dict | None] = mapped_column(JSONVariant, nullable=True)
    ip_origen: Mapped[str | None] = mapped_column(String(45), nullable=True)
    created_at: Mapped[datetime] = _created_at_column()


class ReportExportModel(Base):
    __tablename__ = "report_exports"

    id: Mapped[uuid.UUID] = _uuid_pk()
    usuario_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False)
    tipo_reporte: Mapped[str] = mapped_column(String(50), nullable=False)
    fecha_desde: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    fecha_hasta: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    archivo_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = _created_at_column()


class FirmwareReleaseModel(Base):
    """HU-46: metadata de una versión de firmware preparada para despliegue OTA.

    Simulado a nivel de aplicación: este repositorio no contiene firmware real
    de ESP32 ni un canal MQTT de producción; no se cifra ni transmite ningún
    binario. Ver 08_hu43_47_ota_y_cierre.md para el alcance exacto."""

    __tablename__ = "firmware_releases"

    id: Mapped[uuid.UUID] = _uuid_pk()
    version: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    hash_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    descripcion: Mapped[str] = mapped_column(Text, nullable=False)
    fecha_compilacion: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = _created_at_column()


class FirmwareDeploymentModel(Base):
    __tablename__ = "firmware_deployments"

    id: Mapped[uuid.UUID] = _uuid_pk()
    device_id: Mapped[str] = mapped_column(String(50), ForeignKey("devices.id"), nullable=False)
    version_objetivo: Mapped[str] = mapped_column(String(20), nullable=False)
    estado: Mapped[str] = mapped_column(String(20), nullable=False)
    programado_para: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resultado: Mapped[str | None] = mapped_column(Text, nullable=True)
    completado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = _created_at_column()


class ForensicSnapshotModel(Base):
    """HU-47: snapshot forense persistido ante corrupción detectada en la cadena hash."""

    __tablename__ = "forensic_snapshots"

    id: Mapped[uuid.UUID] = _uuid_pk()
    registro_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("traceability_records.id"), nullable=True
    )
    detalle: Mapped[dict] = mapped_column(JSONVariant, nullable=False)
    created_at: Mapped[datetime] = _created_at_column()


class SystemStateModel(Base):
    """HU-47: fila única (id=1) con el flag global cadena_comprometida."""

    __tablename__ = "system_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cadena_comprometida: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, server_default=func.now())
