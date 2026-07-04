import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, String, Text, Uuid, func
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
    created_at: Mapped[datetime] = _created_at_column()

    rol: Mapped[RoleModel] = relationship(back_populates="usuarios")


class ThermalReadingModel(Base):
    __tablename__ = "thermal_readings"

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
    created_at: Mapped[datetime] = _created_at_column()

    device: Mapped[DeviceModel] = relationship(back_populates="lecturas")
    alertas: Mapped[list["ThermalAlertModel"]] = relationship(back_populates="lectura")


class ThermalAlertModel(Base):
    __tablename__ = "thermal_alerts"

    id: Mapped[uuid.UUID] = _uuid_pk()
    reading_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("thermal_readings.id"), nullable=False)
    device_id: Mapped[str] = mapped_column(String(50), ForeignKey("devices.id"), nullable=False, index=True)
    nivel_riesgo: Mapped[str] = mapped_column(String(30), nullable=False)
    mensaje: Mapped[str] = mapped_column(Text, nullable=False)
    revisada: Mapped[bool] = mapped_column(Boolean, default=False)
    revisada_por: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = _created_at_column()

    lectura: Mapped[ThermalReadingModel] = relationship(back_populates="alertas")
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
