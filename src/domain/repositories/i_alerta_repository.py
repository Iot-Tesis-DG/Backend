from abc import ABC, abstractmethod
from datetime import datetime
from uuid import UUID

from src.domain.entities.alerta_termica import AlertaTermica
from src.domain.value_objects.nivel_riesgo import NivelRiesgo


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
        desde: datetime | None = None,
        hasta: datetime | None = None,
        limite: int = 100,
        offset: int = 0,
    ) -> list[AlertaTermica]: ...

    @abstractmethod
    async def actualizar(self, alerta: AlertaTermica) -> AlertaTermica: ...

    @abstractmethod
    async def obtener_episodio_abierto(self, device_id: str) -> AlertaTermica | None:
        """AIV-02: el episodio de alerta actualmente abierto para el
        dispositivo (a lo sumo uno en la práctica, dado que un dispositivo
        tiene un único nivel_riesgo por lectura)."""
        ...

    @abstractmethod
    async def obtener_ultimo_cerrado(
        self, device_id: str, nivel_riesgo: NivelRiesgo
    ) -> AlertaTermica | None:
        """AIV-02: el episodio cerrado más reciente de este dispositivo y
        tipo de riesgo, para decidir si reabrirlo dentro de la ventana de
        cooldown en vez de crear una alerta nueva."""
        ...
