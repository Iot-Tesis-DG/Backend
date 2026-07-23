from dataclasses import dataclass

from src.domain.repositories.i_trazabilidad_repository import ITrazabilidadRepository
from src.domain.value_objects.hash_encadenado import GENESIS_HASH, HashEncadenado, timestamp_canonico


@dataclass(frozen=True, slots=True)
class ResultadoVerificacion:
    integra: bool
    total_registros: int
    primer_registro_inconsistente: int | None


class VerificarIntegridadRegistroUseCase:
    """RF-15: expone la verificación de consistencia de la cadena de hashes histórica."""

    def __init__(self, trazabilidad_repository: ITrazabilidadRepository) -> None:
        self._trazabilidad_repository = trazabilidad_repository

    async def execute(self) -> ResultadoVerificacion:
        registros = await self._trazabilidad_repository.listar_todos_ordenados()

        previous_hash = GENESIS_HASH
        for indice, registro in enumerate(registros):
            esperado = HashEncadenado.calcular_hash(
                previous_hash, timestamp_canonico(registro.timestamp), registro.payload
            )
            if registro.previous_hash != previous_hash or registro.hash_actual != esperado:
                return ResultadoVerificacion(
                    integra=False,
                    total_registros=len(registros),
                    primer_registro_inconsistente=indice,
                )
            previous_hash = registro.hash_actual

        return ResultadoVerificacion(
            integra=True, total_registros=len(registros), primer_registro_inconsistente=None
        )
