from uuid import UUID

from fastapi import APIRouter, Depends, Query

from src.application.use_cases.gestionar_corrupcion_cadena import AislarCorrupcionUseCase
from src.application.use_cases.registrar_hash_encadenado import RegistrarHashEncadenadoUseCase
from src.application.use_cases.verificar_integridad_registro import VerificarIntegridadRegistroUseCase
from src.domain.value_objects.rol import Rol
from src.infrastructure.database.repositories.corrupcion_repository import SQLAlchemyCorrupcionRepository
from src.infrastructure.database.repositories.trazabilidad_repository import (
    SQLAlchemyTrazabilidadRepository,
)
from src.interface.api.api_protection import limitar_por_usuario
from src.interface.api.deps import DbSessionDep, require_roles
from src.interface.api.mappers import trazabilidad_to_response
from src.interface.api.schemas import (
    DetalleInconsistenciaResponse,
    EstadoCadenaResponse,
    TrazabilidadResponse,
    VerificacionIntegridadResponse,
)

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


@router.get(
    "/verificar",
    response_model=VerificacionIntegridadResponse,
    # B13: la verificación recorre y rehashea la cadena entera — es O(n) sobre
    # una tabla que solo crece. Sin cuota propia, un usuario autenticado podría
    # dejar la API sin CPU con un puñado de peticiones concurrentes. La clave es
    # el usuario y no la IP: en una farmacia todos salen por la misma.
    dependencies=[limitar_por_usuario("trazabilidad_verificar", 5, 60)],
)
async def verificar_integridad(
    session: DbSessionDep,
    _usuario=Depends(require_roles(Rol.TECNICO, Rol.FARMACEUTICO)),
) -> VerificacionIntegridadResponse:
    """HU-26 + HU-47 Escenarios 1-2: si detecta corrupción, además notifica
    (flag global, snapshot forense, evento de emergencia encadenado)."""
    repositorio = SQLAlchemyTrazabilidadRepository(session)
    use_case = VerificarIntegridadRegistroUseCase(
        repositorio,
        SQLAlchemyCorrupcionRepository(session),
        RegistrarHashEncadenadoUseCase(repositorio),
    )
    resultado = await use_case.execute()
    await session.commit()
    detalle = None
    if resultado.detalle_inconsistencia is not None:
        d = resultado.detalle_inconsistencia
        detalle = DetalleInconsistenciaResponse(
            id=d.id, tipo_evento=d.tipo_evento, timestamp=d.timestamp,
            hash_esperado=d.hash_esperado, hash_almacenado=d.hash_almacenado, mensaje=d.mensaje,
        )
    return VerificacionIntegridadResponse(
        integra=resultado.integra,
        total_registros=resultado.total_registros,
        primer_registro_inconsistente=resultado.primer_registro_inconsistente,
        detalle_inconsistencia=detalle,
        registros_posteriores_afectados=resultado.registros_posteriores_afectados,
    )


@router.get("/estado", response_model=EstadoCadenaResponse)
async def obtener_estado_cadena(
    session: DbSessionDep,
    _usuario=Depends(require_roles(Rol.TECNICO, Rol.FARMACEUTICO)),
) -> EstadoCadenaResponse:
    """HU-47 Escenario 2: banner de advertencia en dashboards mientras cadena_comprometida=true."""
    comprometida = await SQLAlchemyCorrupcionRepository(session).cadena_comprometida()
    return EstadoCadenaResponse(cadena_comprometida=comprometida)


@router.post("/corrupcion/{registro_id}/aislar", status_code=204)
async def aislar_corrupcion(
    registro_id: UUID,
    session: DbSessionDep,
    _admin=Depends(require_roles(Rol.ADMINISTRADOR)),
) -> None:
    """HU-47 Escenario 4, Opción 2 (Quarantine)."""
    repositorio = SQLAlchemyTrazabilidadRepository(session)
    use_case = AislarCorrupcionUseCase(
        repositorio,
        SQLAlchemyCorrupcionRepository(session),
        RegistrarHashEncadenadoUseCase(repositorio),
    )
    await use_case.execute(registro_id)
    await session.commit()
