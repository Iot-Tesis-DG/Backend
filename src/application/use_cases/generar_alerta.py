from uuid import UUID

from src.domain.entities.alerta_termica import AlertaTermica
from src.domain.repositories.i_alerta_repository import IAlertaRepository
from src.domain.value_objects.nivel_riesgo import NivelRiesgo

MENSAJES_POR_RIESGO = {
    NivelRiesgo.RIESGO_PREVENTIVO: "Riesgo preventivo: la temperatura se acerca al límite del rango 2-8 C.",
    NivelRiesgo.EXCURSION_CRITICA: "Excursión crítica: la temperatura está fuera del rango 2-8 C.",
}


class GenerarAlertaUseCase:
    """RF-09: genera una alerta cuando la clasificación no es 'normal'."""

    def __init__(self, alerta_repository: IAlertaRepository) -> None:
        self._alerta_repository = alerta_repository

    async def execute(
        self, reading_id: UUID, device_id: str, nivel_riesgo: NivelRiesgo
    ) -> AlertaTermica | None:
        if nivel_riesgo == NivelRiesgo.NORMAL:
            return None

        alerta = AlertaTermica(
            reading_id=reading_id,
            device_id=device_id,
            nivel_riesgo=nivel_riesgo,
            mensaje=MENSAJES_POR_RIESGO[nivel_riesgo],
        )
        return await self._alerta_repository.agregar(alerta)
