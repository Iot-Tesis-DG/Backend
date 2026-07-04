from uuid import UUID

from src.domain.entities.accion_correctiva import AccionCorrectiva
from src.domain.exceptions import RecursoNoEncontradoError
from src.domain.repositories.i_accion_correctiva_repository import IAccionCorrectivaRepository
from src.domain.repositories.i_alerta_repository import IAlertaRepository
from src.domain.repositories.i_trazabilidad_repository import ITrazabilidadRepository
from src.application.use_cases.registrar_hash_encadenado import RegistrarHashEncadenadoUseCase


class RegistrarAccionCorrectivaUseCase:
    """RF-10: el usuario responsable registra una acción correctiva asociada a una alerta activa."""

    def __init__(
        self,
        accion_repository: IAccionCorrectivaRepository,
        alerta_repository: IAlertaRepository,
        trazabilidad_repository: ITrazabilidadRepository,
    ) -> None:
        self._accion_repository = accion_repository
        self._alerta_repository = alerta_repository
        self._registrar_hash = RegistrarHashEncadenadoUseCase(trazabilidad_repository)

    async def execute(self, alert_id: UUID, usuario_id: UUID, descripcion: str) -> AccionCorrectiva:
        alerta = await self._alerta_repository.obtener_por_id(alert_id)
        if alerta is None:
            raise RecursoNoEncontradoError(f"Alerta {alert_id} no encontrada")

        accion = AccionCorrectiva(alert_id=alert_id, usuario_id=usuario_id, descripcion=descripcion)
        accion_creada = await self._accion_repository.agregar(accion)

        await self._registrar_hash.execute(
            tipo_evento="ACCION_CORRECTIVA",
            payload={
                "alert_id": str(alert_id),
                "usuario_id": str(usuario_id),
                "descripcion": descripcion,
            },
            device_id=alerta.device_id,
            usuario_id=usuario_id,
        )
        return accion_creada
