from fastapi import APIRouter, Depends, Query

from src.domain.value_objects.rol import Rol
from src.infrastructure.database.repositories.audit_log_repository import SQLAlchemyAuditLogRepository
from src.interface.api.deps import DbSessionDep, require_roles
from src.interface.api.schemas import AuditLogResponse

router = APIRouter(prefix="/api/auditoria", tags=["auditoria"])


@router.get("", response_model=list[AuditLogResponse])
async def listar_auditoria(
    session: DbSessionDep,
    _admin=Depends(require_roles(Rol.ADMINISTRADOR)),
    limite: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> list[AuditLogResponse]:
    repositorio = SQLAlchemyAuditLogRepository(session)
    registros = await repositorio.listar(limite=limite, offset=offset)
    return [AuditLogResponse(**registro) for registro in registros]
