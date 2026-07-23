from datetime import datetime, timezone

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
