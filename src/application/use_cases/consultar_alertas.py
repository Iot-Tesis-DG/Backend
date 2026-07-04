from uuid import UUID

from src.domain.entities.alerta_termica import AlertaTermica
from src.domain.exceptions import RecursoNoEncontradoError
from src.domain.repositories.i_alerta_repository import IAlertaRepository


class ConsultarAlertasUseCase:
    def __init__(self, alerta_repository: IAlertaRepository) -> None:
        self._alerta_repository = alerta_repository

    async def execute(
        self,
        device_id: str | None = None,
        revisada: bool | None = None,
        limite: int = 100,
        offset: int = 0,
    ) -> list[AlertaTermica]:
        return await self._alerta_repository.listar(
            device_id=device_id, revisada=revisada, limite=limite, offset=offset
        )


class MarcarAlertaRevisadaUseCase:
    def __init__(self, alerta_repository: IAlertaRepository) -> None:
        self._alerta_repository = alerta_repository

    async def execute(self, alerta_id: UUID, usuario_id: UUID) -> AlertaTermica:
        alerta = await self._alerta_repository.obtener_por_id(alerta_id)
        if alerta is None:
            raise RecursoNoEncontradoError(f"Alerta {alerta_id} no encontrada")
        alerta.marcar_revisada(usuario_id)
        return await self._alerta_repository.actualizar(alerta)
