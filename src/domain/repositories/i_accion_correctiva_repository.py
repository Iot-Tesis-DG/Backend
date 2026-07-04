from abc import ABC, abstractmethod

from src.domain.entities.accion_correctiva import AccionCorrectiva


class IAccionCorrectivaRepository(ABC):
    @abstractmethod
    async def agregar(self, accion: AccionCorrectiva) -> AccionCorrectiva: ...

    @abstractmethod
    async def listar_por_alerta(self, alert_id) -> list[AccionCorrectiva]: ...
