from abc import ABC, abstractmethod
from uuid import UUID


class IAuditLogRepository(ABC):
    @abstractmethod
    async def registrar(
        self,
        usuario_id: UUID | None,
        accion: str,
        recurso: str,
        detalle: dict,
        ip_origen: str | None = None,
    ) -> None: ...

    @abstractmethod
    async def listar(self, limite: int = 100, offset: int = 0) -> list[dict]: ...
