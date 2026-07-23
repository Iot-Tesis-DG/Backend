from datetime import datetime, timezone
from uuid import UUID

from src.application.use_cases.registrar_hash_encadenado import RegistrarHashEncadenadoUseCase
from src.domain.repositories.i_corrupcion_repository import ICorrupcionRepository
from src.domain.repositories.i_trazabilidad_repository import ITrazabilidadRepository
from src.domain.value_objects.hash_encadenado import GENESIS_HASH


class AislarCorrupcionUseCase:
    """HU-47 Escenario 4, Opción 2 (Aislamiento/Quarantine).

    Las otras dos opciones del escenario (restauración desde backup físico y
    modo forense de solo-lectura) son procedimientos operativos que requieren
    actuar sobre la infraestructura de base de datos fuera del proceso de la
    API (pg_restore, congelar despliegues) — se documentan como runbook manual
    en 08_hu43_47_ota_y_cierre.md en vez de simularse como un botón que no
    ejecuta lo que promete. Esta opción sí queda completamente implementada
    porque solo depende de datos que la propia aplicación controla.
    """

    def __init__(
        self,
        trazabilidad_repository: ITrazabilidadRepository,
        corrupcion_repository: ICorrupcionRepository,
        registrar_hash: RegistrarHashEncadenadoUseCase,
    ) -> None:
        self._trazabilidad_repository = trazabilidad_repository
        self._corrupcion_repository = corrupcion_repository
        self._registrar_hash = registrar_hash

    async def execute(self, registro_corrupto_id: UUID) -> None:
        registros = await self._trazabilidad_repository.listar_todos_ordenados()
        ids_posteriores: list[UUID] = []
        encontrado = False
        for registro in registros:
            if encontrado:
                ids_posteriores.append(registro.id)
            if registro.id == registro_corrupto_id:
                encontrado = True

        await self._trazabilidad_repository.marcar_corrupto(registro_corrupto_id)
        await self._trazabilidad_repository.marcar_posteriores_como_afectados(ids_posteriores)

        # Bloque génesis: los registros futuros inician una cadena nueva e
        # independiente. El histórico hasta el punto de ruptura exacto sigue
        # siendo íntegro y verificable; solo el bloque corrupto y lo posterior
        # que dependía de él quedan marcados como "Cadena Rota / Aislada".
        await self._registrar_hash.execute(
            tipo_evento="REGISTRO_AISLADO_CORRUPCION",
            payload={
                "registro_corrupto_id": str(registro_corrupto_id),
                "registros_afectados": len(ids_posteriores),
            },
            timestamp=datetime.now(tz=timezone.utc),
            previous_hash_forzado=GENESIS_HASH,
        )
        await self._corrupcion_repository.marcar_restaurada()
