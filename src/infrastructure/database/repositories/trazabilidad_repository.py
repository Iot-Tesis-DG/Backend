from datetime import datetime
from uuid import UUID

from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.entities.registro_trazabilidad import RegistroTrazabilidad
from src.domain.repositories.i_trazabilidad_repository import ITrazabilidadRepository
from src.domain.value_objects.hash_encadenado import GENESIS_HASH, HashEncadenado
from src.infrastructure.database.models import TraceabilityRecordModel

# Clave arbitraria fija para el candado consultivo de PostgreSQL que serializa
# la sección crítica "leer último hash + insertar siguiente eslabón" a nivel de
# base de datos. Complementa (no sustituye) el asyncio.Lock de proceso en
# RegistrarHashEncadenadoUseCase: el lock de proceso alcanza para un único
# worker; pg_advisory_xact_lock además protege ante múltiples workers/instancias
# escribiendo contra la misma base de datos. Se libera automáticamente al
# terminar la transacción (variante _xact_). No tiene efecto en SQLite (los
# tests con aiosqlite omiten esta sentencia, ver dialect check abajo).
_CLAVE_CANDADO_CADENA_HASH = 911777001


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
        if self._session.bind is not None and self._session.bind.dialect.name == "postgresql":
            # Defensa en profundidad multi-worker: serializa a nivel de BD.
            await self._session.execute(
                text("SELECT pg_advisory_xact_lock(:clave)"),
                {"clave": _CLAVE_CANDADO_CADENA_HASH},
            )
        # Desempate por `id` además de `created_at`.
        #
        # `created_at` se genera en Python con resolución de microsegundos, así
        # que un empate es improbable — pero no imposible. Y si ocurriera, lo
        # grave no es el empate en sí: es que ESTA consulta (camino de
        # escritura, DESC) y `listar_todos_ordenados()` (camino de
        # verificación, ASC) podrían resolverlo en sentidos distintos. La
        # cadena se habría escrito en un orden y se verificaría en otro,
        # denunciando una corrupción inexistente sobre evidencia intacta.
        #
        # `id` es un UUID4, no monótono: no aporta orden cronológico. Aporta lo
        # único que hace falta aquí, que es que ambos caminos desempaten igual.
        stmt = select(TraceabilityRecordModel.hash_actual).order_by(
            TraceabilityRecordModel.created_at.desc(),
            TraceabilityRecordModel.id.desc(),
        ).limit(1)
        result = await self._session.execute(stmt)
        hash_actual = result.scalar_one_or_none()
        return hash_actual or GENESIS_HASH

    async def listar_todos_ordenados(self) -> list[RegistroTrazabilidad]:
        # Mismo criterio de desempate que `obtener_ultimo_hash()`, en sentido
        # inverso: los dos caminos deben recorrer la cadena en el mismo orden.
        stmt = select(TraceabilityRecordModel).order_by(
            TraceabilityRecordModel.created_at.asc(),
            TraceabilityRecordModel.id.asc(),
        )
        result = await self._session.execute(stmt)
        return [_to_entity(m) for m in result.scalars().all()]

    async def listar(
        self,
        tipo_evento: str | None = None,
        device_id: str | None = None,
        desde: datetime | None = None,
        hasta: datetime | None = None,
        limite: int = 100,
        offset: int = 0,
    ) -> list[RegistroTrazabilidad]:
        stmt = select(TraceabilityRecordModel)
        if tipo_evento:
            stmt = stmt.where(TraceabilityRecordModel.tipo_evento == tipo_evento)
        if device_id:
            stmt = stmt.where(TraceabilityRecordModel.device_id == device_id)
        # Mismo motivo que en alertas: el reporte BPA debe ceñirse al periodo.
        # Se filtra por `timestamp` (el instante del hecho registrado), que es
        # el campo que el propio reporte muestra al auditor.
        if desde is not None:
            stmt = stmt.where(TraceabilityRecordModel.timestamp >= desde)
        if hasta is not None:
            stmt = stmt.where(TraceabilityRecordModel.timestamp <= hasta)
        stmt = stmt.order_by(TraceabilityRecordModel.created_at.desc()).limit(limite).offset(offset)
        result = await self._session.execute(stmt)
        return [_to_entity(m) for m in result.scalars().all()]

    async def marcar_corrupto(self, registro_id: UUID) -> None:
        await self._session.execute(
            update(TraceabilityRecordModel)
            .where(TraceabilityRecordModel.id == registro_id)
            .values(is_corrupted=True)
        )
        await self._session.flush()

    async def marcar_posteriores_como_afectados(self, ids: list[UUID]) -> None:
        if not ids:
            return
        await self._session.execute(
            update(TraceabilityRecordModel)
            .where(TraceabilityRecordModel.id.in_(ids))
            .values(is_after_corruption=True)
        )
        await self._session.flush()
