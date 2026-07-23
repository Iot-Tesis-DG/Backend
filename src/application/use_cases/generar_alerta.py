from datetime import datetime, timedelta, timezone
from uuid import UUID

from src.domain.entities.alerta_termica import AlertaTermica
from src.domain.repositories.i_alerta_repository import IAlertaRepository
from src.domain.value_objects.nivel_riesgo import NivelRiesgo

MENSAJES_POR_RIESGO = {
    NivelRiesgo.RIESGO_PREVENTIVO: "Riesgo preventivo: la temperatura se acerca al límite del rango 2-8 C.",
    NivelRiesgo.EXCURSION_CRITICA: "Excursión crítica: la temperatura está fuera del rango 2-8 C.",
}

# AIV-02: ventana de cooldown — un episodio recién cerrado del mismo
# dispositivo y tipo de riesgo se reabre (no se crea uno nuevo) si la
# siguiente lectura crítica llega dentro de esta ventana, evitando flapping
# de apertura/cierre por una única lectura normal aislada (histéresis).
COOLDOWN_MINUTOS = 15


def _a_utc(valor: datetime) -> datetime:
    return valor if valor.tzinfo is not None else valor.replace(tzinfo=timezone.utc)


class GenerarAlertaUseCase:
    """RF-09: gestiona el EPISODIO de alerta por dispositivo+tipo de riesgo,
    no una alerta por lectura (corrige AIV-02, "tormenta de alertas").

    Reglas:
    - Una lectura NORMAL cierra el episodio abierto del dispositivo (evento
      de recuperación), sin crear ninguna fila nueva.
    - Una lectura crítica del MISMO tipo que el episodio ya abierto solo
      actualiza ese episodio (lectura más reciente + timestamp).
    - Una lectura crítica de OTRO tipo (escalamiento/desescalamiento) cierra
      el episodio anterior y abre uno nuevo.
    - Sin episodio abierto: si el último episodio CERRADO del mismo
      dispositivo+tipo terminó hace menos de COOLDOWN_MINUTOS, se reabre en
      vez de crear una fila nueva. Si no, se crea una alerta nueva.
    """

    def __init__(self, alerta_repository: IAlertaRepository) -> None:
        self._alerta_repository = alerta_repository

    async def execute(
        self,
        reading_id: UUID,
        device_id: str,
        nivel_riesgo: NivelRiesgo | None,
        timestamp: datetime,
    ) -> AlertaTermica | None:
        episodio_abierto = await self._alerta_repository.obtener_episodio_abierto(device_id)

        if nivel_riesgo is None or nivel_riesgo == NivelRiesgo.NORMAL:
            if episodio_abierto is not None:
                episodio_abierto.cerrar(timestamp)
                await self._alerta_repository.actualizar(episodio_abierto)
            return None

        if episodio_abierto is not None:
            if episodio_abierto.nivel_riesgo == nivel_riesgo:
                episodio_abierto.registrar_lectura(reading_id, timestamp)
                return await self._alerta_repository.actualizar(episodio_abierto)
            # Escalamiento/desescalamiento: cierra el episodio anterior antes
            # de evaluar si corresponde abrir/reabrir uno del nuevo tipo.
            episodio_abierto.cerrar(timestamp)
            await self._alerta_repository.actualizar(episodio_abierto)

        ultimo_cerrado = await self._alerta_repository.obtener_ultimo_cerrado(device_id, nivel_riesgo)
        if (
            ultimo_cerrado is not None
            and ultimo_cerrado.cerrada_en is not None
            and (_a_utc(timestamp) - _a_utc(ultimo_cerrado.cerrada_en)) <= timedelta(minutes=COOLDOWN_MINUTOS)
        ):
            ultimo_cerrado.reabrir(reading_id, timestamp)
            return await self._alerta_repository.actualizar(ultimo_cerrado)

        alerta = AlertaTermica(
            reading_id=reading_id,
            device_id=device_id,
            nivel_riesgo=nivel_riesgo,
            mensaje=MENSAJES_POR_RIESGO[nivel_riesgo],
            lectura_inicial_id=reading_id,
            lectura_mas_reciente_id=reading_id,
            ultima_actualizacion=timestamp,
        )
        return await self._alerta_repository.agregar(alerta)
