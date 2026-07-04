from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.entities.registro_trazabilidad import RegistroTrazabilidad
from src.domain.repositories.i_trazabilidad_repository import ITrazabilidadRepository
from src.domain.value_objects.hash_encadenado import GENESIS_HASH, HashEncadenado
from src.infrastructure.database.models import TraceabilityRecordModel


def _to_entity(model: TraceabilityRecordModel) -> RegistroTrazabilidad:
    return RegistroTrazabilidad(
        id=model.id,
        tipo_evento=model.tipo_evento,
        payload=model.payload,
        timestamp=model.timestamp,
        hash_encadenado=HashEncadenado(previous_hash=model.previous_hash, hash_actual=model.hash_actual),
        device_id=model.device_id,
        usuario_id=model.usuario_id,
    )


class SQLAlchemyTrazabilidadRepository(ITrazabilidadRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def agregar(self, registro: RegistroTrazabilidad) -> RegistroTrazabilidad:
        model = TraceabilityRecordModel(
            tipo_evento=registro.tipo_evento,
            device_id=registro.device_id,
            usuario_id=registro.usuario_id,
            payload=registro.payload,
            timestamp=registro.timestamp,
            previous_hash=registro.previous_hash,
            hash_actual=registro.hash_actual,
        )
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)
        return _to_entity(model)

    async def obtener_ultimo_hash(self) -> str:
        stmt = select(TraceabilityRecordModel.hash_actual).order_by(
            TraceabilityRecordModel.created_at.desc()
        ).limit(1)
        result = await self._session.execute(stmt)
        hash_actual = result.scalar_one_or_none()
        return hash_actual or GENESIS_HASH

    async def listar_todos_ordenados(self) -> list[RegistroTrazabilidad]:
        stmt = select(TraceabilityRecordModel).order_by(TraceabilityRecordModel.created_at.asc())
        result = await self._session.execute(stmt)
        return [_to_entity(m) for m in result.scalars().all()]

    async def listar(
        self,
        tipo_evento: str | None = None,
        device_id: str | None = None,
        limite: int = 100,
        offset: int = 0,
    ) -> list[RegistroTrazabilidad]:
        stmt = select(TraceabilityRecordModel)
        if tipo_evento:
            stmt = stmt.where(TraceabilityRecordModel.tipo_evento == tipo_evento)
        if device_id:
            stmt = stmt.where(TraceabilityRecordModel.device_id == device_id)
        stmt = stmt.order_by(TraceabilityRecordModel.created_at.desc()).limit(limite).offset(offset)
        result = await self._session.execute(stmt)
        return [_to_entity(m) for m in result.scalars().all()]
