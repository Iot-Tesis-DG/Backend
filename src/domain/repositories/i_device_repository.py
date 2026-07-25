from abc import ABC, abstractmethod
from datetime import date, datetime


class IDeviceRepository(ABC):
    @abstractmethod
    async def existe(self, device_id: str) -> bool: ...

    @abstractmethod
    async def obtener_o_crear(self, device_id: str) -> dict: ...

    @abstractmethod
    async def actualizar_estado_conectividad(self, device_id: str, estado: str) -> None: ...

    @abstractmethod
    async def listar(self) -> list[dict]: ...

    @abstractmethod
    async def obtener(self, device_id: str) -> dict | None: ...

    @abstractmethod
    async def dar_de_baja(
        self,
        device_id: str,
        motivo: str,
        descripcion: str | None,
        device_id_reemplazo: str | None,
        cuando: datetime,
    ) -> dict: ...

    @abstractmethod
    async def vincular_reemplazo(self, device_id_nuevo: str, device_id_anterior: str) -> None: ...

    @abstractmethod
    async def actualizar_firmware_version(self, device_id: str, version: str) -> None: ...

    # ── HU-30: calibración de sensores ────────────────────────────────────
    @abstractmethod
    async def registrar_calibracion(
        self,
        device_id: str,
        fecha_calibracion: date,
        numero_certificado: str,
        fecha_proxima: date,
        observaciones: str | None,
    ) -> dict: ...

    @abstractmethod
    async def listar_calibracion_vencida(self, hoy: date) -> list[dict]: ...

    @abstractmethod
    async def listar_calibracion_proxima(self, desde: date, hasta: date) -> list[dict]: ...
