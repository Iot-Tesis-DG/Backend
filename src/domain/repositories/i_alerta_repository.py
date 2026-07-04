from abc import ABC, abstractmethod
from uuid import UUID

from src.domain.entities.alerta_termica import AlertaTermica


class IAlertaRepository(ABC):
    @abstractmethod
    async def agregar(self, alerta: AlertaTermica) -> AlertaTermica: ...

    @abstractmethod
    async def obtener_por_id(self, alerta_id: UUID) -> AlertaTermica | None: ...

    @abstractmethod
    async def listar(
        self,
        device_id: str | None = None,
        revisada: bool | None = None,
        limite: int = 100,
        offset: int = 0,
    ) -> list[AlertaTermica]: ...

    @abstractmethod
    async def actualizar(self, alerta: AlertaTermica) -> AlertaTermica: ...
