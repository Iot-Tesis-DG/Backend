from abc import ABC, abstractmethod


class IDeviceRepository(ABC):
    @abstractmethod
    async def obtener_o_crear(self, device_id: str) -> dict: ...

    @abstractmethod
    async def actualizar_estado_conectividad(self, device_id: str, estado: str) -> None: ...

    @abstractmethod
    async def listar(self) -> list[dict]: ...
