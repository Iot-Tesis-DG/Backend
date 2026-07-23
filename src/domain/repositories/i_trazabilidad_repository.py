from abc import ABC, abstractmethod
from uuid import UUID

from src.domain.entities.registro_trazabilidad import RegistroTrazabilidad


class ITrazabilidadRepository(ABC):
    @abstractmethod
    async def agregar(self, registro: RegistroTrazabilidad) -> RegistroTrazabilidad: ...

    @abstractmethod
    async def marcar_corrupto(self, registro_id: UUID) -> None: ...

    @abstractmethod
    async def marcar_posteriores_como_afectados(self, ids: list[UUID]) -> None: ...

    @abstractmethod
    async def obtener_ultimo_hash(self) -> str:
        """Devuelve GENESIS_HASH si la cadena aún no tiene registros."""
        ...

    @abstractmethod
    async def listar_todos_ordenados(self) -> list[RegistroTrazabilidad]: ...

    @abstractmethod
    async def listar(
        self,
        tipo_evento: str | None = None,
        device_id: str | None = None,
        limite: int = 100,
        offset: int = 0,
    ) -> list[RegistroTrazabilidad]: ...
