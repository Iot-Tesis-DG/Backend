from fastapi import APIRouter, Depends, HTTPException, Request, status

from src.application.use_cases.auditar_accion_critica import AuditarAccionCriticaUseCase
from src.application.use_cases.gestionar_dispositivos import DarDeBajaDispositivoUseCase
from src.application.use_cases.registrar_hash_encadenado import RegistrarHashEncadenadoUseCase
from src.domain.exceptions import DomainError, RecursoNoEncontradoError
from src.domain.value_objects.rol import Rol
from src.infrastructure.database.repositories.audit_log_repository import SQLAlchemyAuditLogRepository
from src.infrastructure.database.repositories.device_repository import SQLAlchemyDeviceRepository
from src.infrastructure.database.repositories.trazabilidad_repository import (
    SQLAlchemyTrazabilidadRepository,
)
from src.interface.api.deps import DbSessionDep, require_roles
from src.interface.api.schemas import DispositivoBajaRequest, DispositivoResponse

router = APIRouter(prefix="/api/dispositivos", tags=["dispositivos"])

# HU-43 Escenario 4: la HU pide "ADMINISTRADOR o TÉCNICO con permiso especial".
# Este backend no modela permisos granulares por usuario (solo RBAC por rol,
# ver rbac.py), así que se restringe a ADMINISTRADOR — documentado como
# simplificación deliberada en 08_hu43_47_ota_y_cierre.md.
router_dep = require_roles(Rol.ADMINISTRADOR)


@router.get("", response_model=list[DispositivoResponse])
async def listar_dispositivos(session: DbSessionDep, _admin=Depends(router_dep)) -> list[DispositivoResponse]:
    repositorio = SQLAlchemyDeviceRepository(session)
    return [DispositivoResponse(**d) for d in await repositorio.listar()]


@router.post("/{device_id}/baja", response_model=DispositivoResponse)
async def dar_de_baja(
    device_id: str,
    body: DispositivoBajaRequest,
    session: DbSessionDep,
    request: Request,
    admin=Depends(router_dep),
) -> DispositivoResponse:
    repositorio = SQLAlchemyDeviceRepository(session)
    use_case = DarDeBajaDispositivoUseCase(
        repositorio, RegistrarHashEncadenadoUseCase(SQLAlchemyTrazabilidadRepository(session))
    )
    try:
        dispositivo = await use_case.execute(
            device_id, body.motivo, body.descripcion, body.device_id_reemplazo
        )
    except RecursoNoEncontradoError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except DomainError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    ip = request.client.host if request.client else None
    await AuditarAccionCriticaUseCase(SQLAlchemyAuditLogRepository(session)).execute(
        usuario_id=admin.id,
        accion="BAJA_DISPOSITIVO",
        recurso=f"dispositivos/{device_id}",
        detalle={"motivo": body.motivo, "reemplazo": body.device_id_reemplazo},
        ip_origen=ip,
    )
    await session.commit()
    return DispositivoResponse(**dispositivo)
