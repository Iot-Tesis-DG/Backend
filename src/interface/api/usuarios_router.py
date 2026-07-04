from fastapi import APIRouter, Depends, HTTPException, Request, status

from src.application.use_cases.auditar_accion_critica import AuditarAccionCriticaUseCase
from src.application.use_cases.gestionar_usuarios import CrearUsuarioUseCase, ListarUsuariosUseCase
from src.domain.exceptions import DomainError
from src.domain.value_objects.rol import Rol
from src.infrastructure.database.repositories.audit_log_repository import SQLAlchemyAuditLogRepository
from src.infrastructure.database.repositories.usuario_repository import SQLAlchemyUsuarioRepository
from src.interface.api.deps import DbSessionDep, require_roles
from src.interface.api.schemas import UsuarioCreateRequest, UsuarioResponse

router = APIRouter(prefix="/api/usuarios", tags=["usuarios"])


@router.post("", response_model=UsuarioResponse, status_code=status.HTTP_201_CREATED)
async def crear_usuario(
    body: UsuarioCreateRequest,
    session: DbSessionDep,
    request: Request,
    admin=Depends(require_roles(Rol.ADMINISTRADOR)),
) -> UsuarioResponse:
    repositorio = SQLAlchemyUsuarioRepository(session)
    use_case = CrearUsuarioUseCase(repositorio)
    try:
        usuario = await use_case.execute(body.nombre, body.email, body.password, body.rol)
    except DomainError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    auditoria_repository = SQLAlchemyAuditLogRepository(session)
    await AuditarAccionCriticaUseCase(auditoria_repository).execute(
        usuario_id=admin.id,
        accion="CREAR_USUARIO",
        recurso=f"usuarios/{usuario.id}",
        detalle={"email": usuario.email, "rol": usuario.rol.value},
        ip_origen=request.client.host if request.client else None,
    )
    await session.commit()
    return UsuarioResponse(id=usuario.id, nombre=usuario.nombre, email=usuario.email, rol=usuario.rol)


@router.get("", response_model=list[UsuarioResponse])
async def listar_usuarios(
    session: DbSessionDep,
    _admin=Depends(require_roles(Rol.ADMINISTRADOR)),
) -> list[UsuarioResponse]:
    repositorio = SQLAlchemyUsuarioRepository(session)
    use_case = ListarUsuariosUseCase(repositorio)
    usuarios = await use_case.execute()
    return [
        UsuarioResponse(id=u.id, nombre=u.nombre, email=u.email, rol=u.rol) for u in usuarios
    ]
