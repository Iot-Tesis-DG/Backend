from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.entities.alerta_termica import AlertaTermica
from src.domain.repositories.i_alerta_repository import IAlertaRepository
from src.domain.value_objects.nivel_riesgo import NivelRiesgo
from src.infrastructure.database.models import ThermalAlertModel


def _to_entity(model: ThermalAlertModel) -> AlertaTermica:
    return AlertaTermica(
        id=model.id,
        reading_id=model.reading_id,
        device_id=model.device_id,
        nivel_riesgo=NivelRiesgo(model.nivel_riesgo),
        mensaje=model.mensaje,
        revisada=model.revisada,
        revisada_por=model.revisada_por,
        created_at=model.created_at,
    )


class SQLAlchemyAlertaRepository(IAlertaRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def agregar(self, alerta: AlertaTermica) -> AlertaTermica:
        model = ThermalAlertModel(
            reading_id=alerta.reading_id,
            device_id=alerta.device_id,
            nivel_riesgo=alerta.nivel_riesgo.value,
            mensaje=alerta.mensaje,
            revisada=alerta.revisada,
            revisada_por=alerta.revisada_por,
        )
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)
        return _to_entity(model)

    async def obtener_por_id(self, alerta_id: UUID) -> AlertaTermica | None:
        model = await self._session.get(ThermalAlertModel, alerta_id)
        return _to_entity(model) if model else None

    async def listar(
        self,
        device_id: str | None = None,
        revisada: bool | None = None,
        limite: int = 100,
        offset: int = 0,
    ) -> list[AlertaTermica]:
        stmt = select(ThermalAlertModel)
        if device_id:
            stmt = stmt.where(ThermalAlertModel.device_id == device_id)
        if revisada is not None:
            stmt = stmt.where(ThermalAlertModel.revisada == revisada)
        stmt = stmt.order_by(ThermalAlertModel.created_at.desc()).limit(limite).offset(offset)
        result = await self._session.execute(stmt)
        return [_to_entity(m) for m in result.scalars().all()]

    async def actualizar(self, alerta: AlertaTermica) -> AlertaTermica:
        model = await self._session.get(ThermalAlertModel, alerta.id)
        if model is None:
            raise ValueError(f"Alerta {alerta.id} no encontrada")
        model.revisada = alerta.revisada
        model.revisada_por = alerta.revisada_por
        await self._session.flush()
        await self._session.refresh(model)
        return _to_entity(model)
