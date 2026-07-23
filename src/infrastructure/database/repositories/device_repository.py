from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.repositories.i_device_repository import IDeviceRepository
from src.infrastructure.database.models import DeviceModel


def _to_dict(model: DeviceModel) -> dict:
    return {
        "id": model.id,
        "nombre": model.nombre,
        "ubicacion": model.ubicacion,
        "estado_conectividad": model.estado_conectividad,
        "created_at": model.created_at,
        "activo": model.activo,
        "firmware_version": model.firmware_version,
        "motivo_baja": model.motivo_baja,
        "descripcion_baja": model.descripcion_baja,
        "dado_de_baja_en": model.dado_de_baja_en,
        "reemplaza_a_device_id": model.reemplaza_a_device_id,
    }


class SQLAlchemyDeviceRepository(IDeviceRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def existe(self, device_id: str) -> bool:
        return await self._session.get(DeviceModel, device_id) is not None

    async def obtener_o_crear(self, device_id: str) -> dict:
        model = await self._session.get(DeviceModel, device_id)
        if model is None:
            model = DeviceModel(id=device_id)
            self._session.add(model)
            await self._session.flush()
            await self._session.refresh(model)
        return _to_dict(model)

    async def actualizar_estado_conectividad(self, device_id: str, estado: str) -> None:
        model = await self._session.get(DeviceModel, device_id)
        if model is None:
            model = DeviceModel(id=device_id, estado_conectividad=estado)
            self._session.add(model)
        else:
            model.estado_conectividad = estado
        await self._session.flush()

    async def listar(self) -> list[dict]:
        result = await self._session.execute(select(DeviceModel))
        return [_to_dict(m) for m in result.scalars().all()]

    async def obtener(self, device_id: str) -> dict | None:
        model = await self._session.get(DeviceModel, device_id)
        return _to_dict(model) if model else None

    async def dar_de_baja(
        self,
        device_id: str,
        motivo: str,
        descripcion: str | None,
        device_id_reemplazo: str | None,
        cuando: datetime,
    ) -> dict:
        model = await self._session.get(DeviceModel, device_id)
        if model is None:
            raise ValueError(f"Dispositivo {device_id} no encontrado")
        model.activo = False
        model.motivo_baja = motivo
        model.descripcion_baja = descripcion
        model.dado_de_baja_en = cuando
        if device_id_reemplazo:
            model.reemplaza_a_device_id = None  # el vínculo se registra en el dispositivo nuevo, no aquí
        await self._session.flush()
        return _to_dict(model)

    async def vincular_reemplazo(self, device_id_nuevo: str, device_id_anterior: str) -> None:
        model = await self._session.get(DeviceModel, device_id_nuevo)
        if model is None:
            model = DeviceModel(id=device_id_nuevo, reemplaza_a_device_id=device_id_anterior)
            self._session.add(model)
        else:
            model.reemplaza_a_device_id = device_id_anterior
        await self._session.flush()

    async def actualizar_firmware_version(self, device_id: str, version: str) -> None:
        model = await self._session.get(DeviceModel, device_id)
        if model is None:
            raise ValueError(f"Dispositivo {device_id} no encontrado")
        model.firmware_version = version
        await self._session.flush()
