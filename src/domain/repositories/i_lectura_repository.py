from abc import ABC, abstractmethod
from datetime import datetime
from uuid import UUID

from src.domain.entities.lectura_termica import LecturaTermica


class ILecturaRepository(ABC):
    @abstractmethod
    async def agregar(self, lectura: LecturaTermica) -> LecturaTermica: ...

    @abstractmethod
    async def obtener_por_id(self, lectura_id: UUID) -> LecturaTermica | None: ...

    @abstractmethod
    async def listar(
        self,
        device_id: str | None = None,
        nivel_riesgo: str | None = None,
        estado_conectividad: str | None = None,
        desde: datetime | None = None,
        hasta: datetime | None = None,
        limite: int = 100,
        offset: int = 0,
    ) -> list[LecturaTermica]: ...

    @abstractmethod
    async def listar_recientes_por_device(self, device_id: str, limite: int) -> list[LecturaTermica]: ...

    @abstractmethod
    async def obtener_por_device_y_timestamp(
        self, device_id: str, timestamp: datetime
    ) -> LecturaTermica | None:
        """Deduplicación/idempotencia (RF-07): localiza una lectura ya persistida
        para el mismo dispositivo y el mismo instante exacto, de forma que un
        reenvío MQTT (PUBACK perdido, QoS1) no genere un registro duplicado."""
        ...
