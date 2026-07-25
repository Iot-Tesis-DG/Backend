from calendar import monthrange
from datetime import date, datetime, timedelta, timezone
from uuid import UUID

from src.application.use_cases.registrar_hash_encadenado import RegistrarHashEncadenadoUseCase
from src.domain.exceptions import DomainError, RecursoNoEncontradoError
from src.domain.repositories.i_device_repository import IDeviceRepository

_MOTIVOS_BAJA = frozenset({"falla_hardware", "mantenimiento", "reemplazo", "fin_de_servicio"})


class DarDeBajaDispositivoUseCase:
    """HU-43: retira un ESP32/sensor de operación sin corromper la trazabilidad
    histórica — el dispositivo se marca inactivo, sus lecturas y alertas
    previas permanecen intactas, y (si aplica) el reemplazo hereda solo
    lectura del histórico mediante un vínculo explícito en `devices`."""

    def __init__(
        self,
        device_repository: IDeviceRepository,
        registrar_hash: RegistrarHashEncadenadoUseCase,
    ) -> None:
        self._device_repository = device_repository
        self._registrar_hash = registrar_hash

    async def execute(
        self,
        device_id: str,
        motivo: str,
        descripcion: str | None,
        device_id_reemplazo: str | None,
    ) -> dict:
        if motivo not in _MOTIVOS_BAJA:
            raise DomainError(f"Motivo de baja inválido: {motivo}")
        dispositivo = await self._device_repository.obtener(device_id)
        if dispositivo is None:
            raise RecursoNoEncontradoError(f"Dispositivo {device_id} no encontrado")
        if not dispositivo["activo"]:
            raise DomainError("El dispositivo ya está dado de baja")

        cuando = datetime.now(tz=timezone.utc)
        actualizado = await self._device_repository.dar_de_baja(
            device_id, motivo, descripcion, device_id_reemplazo, cuando
        )

        if device_id_reemplazo:
            # Cadena de custodia virtual: el nuevo device_id queda vinculado al
            # anterior para lectura de histórico; inicia su propia cadena hash
            # de lecturas independiente (no se copian ni migran registros).
            await self._device_repository.vincular_reemplazo(device_id_reemplazo, device_id)

        await self._registrar_hash.execute(
            tipo_evento="BAJA_HARDWARE",
            payload={
                "device_id_anterior": device_id,
                "motivo_baja": motivo,
                "device_id_reemplazo_si_existe": device_id_reemplazo,
                "timestamp_baja": cuando.isoformat(),
            },
            device_id=device_id,
        )
        return actualizado


def _sumar_meses(origen: date, meses: int) -> date:
    """Avanza `meses` sobre una fecha sin depender de dateutil. Si el día no
    existe en el mes destino (31 de enero + 1 mes), se ancla al último día
    válido — nunca desborda al mes siguiente."""
    total = origen.month - 1 + meses
    anio = origen.year + total // 12
    mes = total % 12 + 1
    dia_maximo = monthrange(anio, mes)[1]
    return date(anio, mes, min(origen.day, dia_maximo))


class RegistrarCalibracionUseCase:
    """HU-30: deja constancia del certificado de calibración de un sensor.

    Un registro térmico solo sirve como evidencia ante una inspección si el
    instrumento que lo produjo estaba calibrado. Por eso el certificado se
    ancla a la cadena SHA-256 (RF-14): quien audite el histórico puede
    demostrar que la calibración declarada no se alteró después.
    """

    def __init__(
        self,
        device_repository: IDeviceRepository,
        registrar_hash: RegistrarHashEncadenadoUseCase,
    ) -> None:
        self._device_repository = device_repository
        self._registrar_hash = registrar_hash

    async def execute(
        self,
        device_id: str,
        fecha_calibracion: date,
        numero_certificado: str,
        observaciones: str | None,
        meses_vigencia: int,
        usuario_id: UUID | None = None,
    ) -> dict:
        dispositivo = await self._device_repository.obtener(device_id)
        if dispositivo is None:
            raise RecursoNoEncontradoError(f"Dispositivo {device_id} no encontrado")
        if not dispositivo["activo"]:
            raise DomainError("No se puede calibrar un dispositivo dado de baja")

        fecha_proxima = _sumar_meses(fecha_calibracion, meses_vigencia)
        actualizado = await self._device_repository.registrar_calibracion(
            device_id, fecha_calibracion, numero_certificado, fecha_proxima, observaciones
        )

        await self._registrar_hash.execute(
            tipo_evento="CALIBRACION_SENSORES",
            payload={
                "device_id": device_id,
                "fecha_calibracion": fecha_calibracion.isoformat(),
                "numero_certificado": numero_certificado,
                "fecha_proxima_calibracion": fecha_proxima.isoformat(),
                "meses_vigencia": meses_vigencia,
                "observaciones": observaciones,
            },
            device_id=device_id,
            usuario_id=usuario_id,
        )
        return actualizado


class ConsultarEstadoCalibracionUseCase:
    """Dispositivos con certificado vencido o por vencer, para avisar antes de
    que el histórico térmico pierda validez documental."""

    def __init__(self, device_repository: IDeviceRepository) -> None:
        self._device_repository = device_repository

    async def execute(self, hoy: date, dias_preaviso: int = 30) -> dict:
        vencidos = await self._device_repository.listar_calibracion_vencida(hoy)
        proximos = await self._device_repository.listar_calibracion_proxima(
            hoy, hoy + timedelta(days=dias_preaviso)
        )
        return {"vencidos": vencidos, "proximos_a_vencer": proximos}
