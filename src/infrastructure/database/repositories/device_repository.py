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
