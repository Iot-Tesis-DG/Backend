from datetime import datetime, timezone
from uuid import UUID

from src.domain.entities.registro_trazabilidad import RegistroTrazabilidad
from src.domain.repositories.i_trazabilidad_repository import ITrazabilidadRepository
from src.domain.value_objects.hash_encadenado import HashEncadenado


class RegistrarHashEncadenadoUseCase:
    """Genera un nuevo eslabón de la cadena SHA-256 para cualquier evento auditable
    (RF-14: lectura, alerta, acción correctiva, reporte, auditoría, conectividad)."""

    def __init__(self, trazabilidad_repository: ITrazabilidadRepository) -> None:
        self._trazabilidad_repository = trazabilidad_repository

    async def execute(
        self,
        tipo_evento: str,
        payload: dict,
        device_id: str | None = None,
        usuario_id: UUID | None = None,
        timestamp: datetime | None = None,
    ) -> RegistroTrazabilidad:
        timestamp = timestamp or datetime.now(tz=timezone.utc)
        previous_hash = await self._trazabilidad_repository.obtener_ultimo_hash()
        hash_encadenado = HashEncadenado.encadenar(previous_hash, timestamp.isoformat(), payload)

        registro = RegistroTrazabilidad(
            tipo_evento=tipo_evento,
            payload=payload,
            timestamp=timestamp,
            hash_encadenado=hash_encadenado,
            device_id=device_id,
            usuario_id=usuario_id,
        )
        return await self._trazabilidad_repository.agregar(registro)
