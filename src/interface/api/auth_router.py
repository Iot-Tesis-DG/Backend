from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordRequestForm

from src.application.use_cases.auditar_accion_critica import AuditarAccionCriticaUseCase
from src.application.use_cases.autenticar_usuario import AutenticarUsuarioUseCase
from src.domain.exceptions import CredencialesInvalidasError
from src.infrastructure.database.repositories.audit_log_repository import (
    SQLAlchemyAuditLogRepository,
)
from src.infrastructure.database.repositories.usuario_repository import SQLAlchemyUsuarioRepository
from src.interface.api.deps import CurrentUserDep, DbSessionDep, JWTHandlerDep, oauth2_scheme
from src.interface.api.schemas import SSETicketResponse, TokenResponse

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _ip_cliente(request: Request) -> str:
    return request.client.host if request.client else "desconocida"


@router.post("/login", response_model=TokenResponse)
async def login(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    session: DbSessionDep,
    jwt_handler: JWTHandlerDep,
    request: Request,
) -> TokenResponse:
    limiter = request.app.state.login_rate_limiter
    ip = _ip_cliente(request)
    if limiter.bloqueado(ip):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Demasiados intentos fallidos. Intenta nuevamente en unos minutos.",
            headers={"Retry-After": str(limiter.segundos_para_reintentar(ip))},
        )

    usuario_repository = SQLAlchemyUsuarioRepository(session)
    auditoria = AuditarAccionCriticaUseCase(SQLAlchemyAuditLogRepository(session))
    use_case = AutenticarUsuarioUseCase(usuario_repository, jwt_handler)
    try:
        resultado = await use_case.execute(form_data.username, form_data.password)
    except CredencialesInvalidasError as exc:
        limiter.registrar_fallo(ip)
        await auditoria.execute(
            usuario_id=None,
            accion="LOGIN_FALLIDO",
            recurso="auth/login",
            detalle={"email": form_data.username},
            ip_origen=ip,
        )
        await session.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    limiter.reiniciar(ip)
    await auditoria.execute(
        usuario_id=resultado.usuario_id,
        accion="LOGIN_EXITOSO",
        recurso="auth/login",
        detalle={"email": form_data.username},
        ip_origen=ip,
    )
    await session.commit()
    return TokenResponse(access_token=resultado.access_token)


@router.post("/sse-ticket", response_model=SSETicketResponse)
async def emitir_ticket_sse(
    usuario: CurrentUserDep,
    jwt_handler: JWTHandlerDep,
) -> SSETicketResponse:
    """Ticket efímero para abrir el stream SSE (EventSource no envía headers)."""
    return SSETicketResponse(ticket=jwt_handler.crear_ticket_sse(usuario.id))


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    usuario: CurrentUserDep,
    token: Annotated[str, Depends(oauth2_scheme)],
    session: DbSessionDep,
    jwt_handler: JWTHandlerDep,
    request: Request,
) -> Response:
    """Revoca el access token actual (por jti) hasta su expiración natural.

    Sin esto, "cerrar sesión" solo borra el token del cliente; el token seguiría
    siendo válido si fue copiado. La revocación server-side cierra esa ventana.
    """
    payload = jwt_handler.decodificar_token(token)
    request.app.state.token_revocation.registrar(payload.jti, payload.exp.timestamp())

    auditoria = AuditarAccionCriticaUseCase(SQLAlchemyAuditLogRepository(session))
    await auditoria.execute(
        usuario_id=usuario.id,
        accion="LOGOUT",
        recurso="auth/logout",
        detalle=None,
        ip_origen=_ip_cliente(request),
    )
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
