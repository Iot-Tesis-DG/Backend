from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from src.application.use_cases.registrar_hash_encadenado import RegistrarHashEncadenadoUseCase
from src.domain.repositories.i_corrupcion_repository import ICorrupcionRepository
from src.domain.repositories.i_trazabilidad_repository import ITrazabilidadRepository
from src.domain.value_objects.hash_encadenado import GENESIS_HASH, HashEncadenado, timestamp_canonico


@dataclass(frozen=True, slots=True)
class DetalleInconsistencia:
    id: UUID
    tipo_evento: str
    timestamp: datetime
    hash_esperado: str
    hash_almacenado: str
    mensaje: str = "Alteración detectada: el payload fue modificado post-registro"


@dataclass(frozen=True, slots=True)
class ResultadoVerificacion:
    integra: bool
    total_registros: int
    primer_registro_inconsistente: int | None
    detalle_inconsistencia: DetalleInconsistencia | None = None
    registros_posteriores_afectados: int = 0


class VerificarIntegridadRegistroUseCase:
    """RF-15/HU-26: verificación O(n) de la cadena de hashes.

    HU-47 Escenario 1-2: si detecta corrupción, además de reportarla:
    - inserta un evento de emergencia CORRUPCION_CADENA_DETECTADA anclado al
      último hash ÍNTEGRO conocido (no al del bloque corrupto ni al último
      hash almacenado, que puede ya descender de él),
    - activa el flag global `cadena_comprometida` (no detiene la ingesta:
      los registros nuevos se marcan is_after_corruption=True hasta que se
      resuelva, ver ManejarCorrupcionCadenaUseCase),
    - guarda un snapshot forense con la metadata exacta del punto de ruptura.
    """

    def __init__(
        self,
        trazabilidad_repository: ITrazabilidadRepository,
        corrupcion_repository: ICorrupcionRepository | None = None,
        registrar_hash: RegistrarHashEncadenadoUseCase | None = None,
    ) -> None:
        self._trazabilidad_repository = trazabilidad_repository
        self._corrupcion_repository = corrupcion_repository
        self._registrar_hash = registrar_hash

    async def execute(self) -> ResultadoVerificacion:
        registros = await self._trazabilidad_repository.listar_todos_ordenados()

        previous_hash = GENESIS_HASH
        ultimo_hash_integro = GENESIS_HASH
        for indice, registro in enumerate(registros):
            esperado = HashEncadenado.calcular_hash(
                previous_hash, timestamp_canonico(registro.timestamp), registro.payload
            )
            if registro.previous_hash != previous_hash or registro.hash_actual != esperado:
                posteriores = registros[indice + 1 :]
                detalle = DetalleInconsistencia(
                    id=registro.id,
                    tipo_evento=registro.tipo_evento,
                    timestamp=registro.timestamp,
                    hash_esperado=esperado,
                    hash_almacenado=registro.hash_actual,
                )
                await self._notificar_corrupcion(registro.id, detalle, ultimo_hash_integro, len(posteriores))
                return ResultadoVerificacion(
                    integra=False,
                    total_registros=len(registros),
                    primer_registro_inconsistente=indice,
                    detalle_inconsistencia=detalle,
                    registros_posteriores_afectados=len(posteriores),
                )
            previous_hash = registro.hash_actual
            ultimo_hash_integro = registro.hash_actual

        return ResultadoVerificacion(
            integra=True, total_registros=len(registros), primer_registro_inconsistente=None
        )

    async def _notificar_corrupcion(
        self, registro_id: UUID, detalle: DetalleInconsistencia, ultimo_hash_integro: str, posteriores: int
    ) -> None:
        if self._corrupcion_repository is None or self._registrar_hash is None:
            return  # modo solo-lectura (p. ej. reintentos de verificación tras aislar)
        await self._corrupcion_repository.marcar_comprometida()
        await self._corrupcion_repository.guardar_snapshot_forense(
            registro_id,
            {
                "id": str(detalle.id),
                "tipo_evento": detalle.tipo_evento,
                "timestamp": detalle.timestamp.isoformat(),
                "hash_esperado": detalle.hash_esperado,
                "hash_almacenado": detalle.hash_almacenado,
                "registros_posteriores_afectados": posteriores,
            },
        )
        await self._registrar_hash.execute(
            tipo_evento="CORRUPCION_CADENA_DETECTADA",
            payload={
                "registro_corrupto_id": str(detalle.id),
                "hash_esperado": detalle.hash_esperado,
                "hash_almacenado": detalle.hash_almacenado,
                "registros_posteriores_afectados": posteriores,
            },
            timestamp=datetime.now(tz=timezone.utc),
            previous_hash_forzado=ultimo_hash_integro,
        )
