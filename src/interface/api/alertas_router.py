from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from src.application.use_cases.auditar_accion_critica import AuditarAccionCriticaUseCase
from src.application.use_cases.consultar_alertas import ConsultarAlertasUseCase, MarcarAlertaRevisadaUseCase
from src.application.use_cases.registrar_accion_correctiva import RegistrarAccionCorrectivaUseCase
from src.domain.exceptions import RecursoNoEncontradoError
from src.domain.value_objects.rol import Rol
from src.infrastructure.database.repositories.accion_correctiva_repository import (
    SQLAlchemyAccionCorrectivaRepository,
)
from src.infrastructure.database.repositories.alerta_repository import SQLAlchemyAlertaRepository
from src.infrastructure.database.repositories.audit_log_repository import SQLAlchemyAuditLogRepository
from src.infrastructure.database.repositories.trazabilidad_repository import (
    SQLAlchemyTrazabilidadRepository,
)
from src.interface.api.deps import DbSessionDep, require_roles
from src.interface.api.mappers import alerta_to_response
from src.interface.api.schemas import (
    AccionCorrectivaCreateRequest,
    AccionCorrectivaResponse,
    AlertaResponse,
)

router = APIRouter(prefix="/api/alertas", tags=["alertas"])


@router.get("", response_model=list[AlertaResponse])
async def listar_alertas(
    session: DbSessionDep,
    _usuario=Depends(require_roles(Rol.TECNICO, Rol.FARMACEUTICO)),
    device_id: str | None = None,
    revisada: bool | None = None,
    limite: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> list[AlertaResponse]:
    alerta_repository = SQLAlchemyAlertaRepository(session)
    use_case = ConsultarAlertasUseCase(alerta_repository)
    alertas = await use_case.execute(device_id=device_id, revisada=revisada, limite=limite, offset=offset)
    return [alerta_to_response(a) for a in alertas]


@router.patch("/{alerta_id}/revisar", response_model=AlertaResponse)
async def revisar_alerta(
    alerta_id: UUID,
    session: DbSessionDep,
    request: Request,
    usuario=Depends(require_roles(Rol.FARMACEUTICO)),
) -> AlertaResponse:
    alerta_repository = SQLAlchemyAlertaRepository(session)
    use_case = MarcarAlertaRevisadaUseCase(alerta_repository)
    try:
        alerta = await use_case.execute(alerta_id, usuario.id)
    except RecursoNoEncontradoError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    auditoria_repository = SQLAlchemyAuditLogRepository(session)
    await AuditarAccionCriticaUseCase(auditoria_repository).execute(
        usuario_id=usuario.id,
        accion="REVISAR_ALERTA",
        recurso=f"alertas/{alerta_id}",
        detalle={"nivel_riesgo": alerta.nivel_riesgo.value},
        ip_origen=request.client.host if request.client else None,
    )
    await session.commit()
    return alerta_to_response(alerta)


@router.post(
    "/{alerta_id}/acciones-correctivas",
    response_model=AccionCorrectivaResponse,
    status_code=status.HTTP_201_CREATED,
)
async def registrar_accion_correctiva(
    alerta_id: UUID,
    body: AccionCorrectivaCreateRequest,
    session: DbSessionDep,
    request: Request,
    usuario=Depends(require_roles(Rol.TECNICO, Rol.FARMACEUTICO)),
) -> AccionCorrectivaResponse:
    accion_repository = SQLAlchemyAccionCorrectivaRepository(session)
    alerta_repository = SQLAlchemyAlertaRepository(session)
    trazabilidad_repository = SQLAlchemyTrazabilidadRepository(session)
    use_case = RegistrarAccionCorrectivaUseCase(accion_repository, alerta_repository, trazabilidad_repository)
    try:
        accion = await use_case.execute(alerta_id, usuario.id, body.descripcion)
    except RecursoNoEncontradoError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    auditoria_repository = SQLAlchemyAuditLogRepository(session)
    await AuditarAccionCriticaUseCase(auditoria_repository).execute(
        usuario_id=usuario.id,
        accion="REGISTRAR_ACCION_CORRECTIVA",
        recurso=f"alertas/{alerta_id}/acciones-correctivas/{accion.id}",
        detalle={"descripcion": body.descripcion},
        ip_origen=request.client.host if request.client else None,
    )
    await session.commit()
    return AccionCorrectivaResponse(
        id=accion.id,
        alert_id=accion.alert_id,
        usuario_id=accion.usuario_id,
        descripcion=accion.descripcion,
        created_at=accion.created_at,
    )
