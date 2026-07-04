from fastapi import APIRouter, Depends, Query

from src.application.use_cases.verificar_integridad_registro import VerificarIntegridadRegistroUseCase
from src.domain.value_objects.rol import Rol
from src.infrastructure.database.repositories.trazabilidad_repository import (
    SQLAlchemyTrazabilidadRepository,
)
from src.interface.api.deps import DbSessionDep, require_roles
from src.interface.api.mappers import trazabilidad_to_response
from src.interface.api.schemas import TrazabilidadResponse, VerificacionIntegridadResponse

router = APIRouter(prefix="/api/trazabilidad", tags=["trazabilidad"])


@router.get("", response_model=list[TrazabilidadResponse])
async def listar_trazabilidad(
    session: DbSessionDep,
    _usuario=Depends(require_roles(Rol.TECNICO, Rol.FARMACEUTICO)),
    tipo_evento: str | None = None,
    device_id: str | None = None,
    limite: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> list[TrazabilidadResponse]:
    repositorio = SQLAlchemyTrazabilidadRepository(session)
    registros = await repositorio.listar(
        tipo_evento=tipo_evento, device_id=device_id, limite=limite, offset=offset
    )
    return [trazabilidad_to_response(r) for r in registros]


@router.get("/verificar", response_model=VerificacionIntegridadResponse)
async def verificar_integridad(
    session: DbSessionDep,
    _usuario=Depends(require_roles(Rol.TECNICO, Rol.FARMACEUTICO)),
) -> VerificacionIntegridadResponse:
    repositorio = SQLAlchemyTrazabilidadRepository(session)
    use_case = VerificarIntegridadRegistroUseCase(repositorio)
    resultado = await use_case.execute()
    return VerificacionIntegridadResponse(
        integra=resultado.integra,
        total_registros=resultado.total_registros,
        primer_registro_inconsistente=resultado.primer_registro_inconsistente,
    )
