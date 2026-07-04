from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm

from src.application.use_cases.autenticar_usuario import AutenticarUsuarioUseCase
from src.domain.exceptions import CredencialesInvalidasError
from src.infrastructure.database.repositories.usuario_repository import SQLAlchemyUsuarioRepository
from src.interface.api.deps import DbSessionDep, JWTHandlerDep
from src.interface.api.schemas import TokenResponse

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
async def login(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    session: DbSessionDep,
    jwt_handler: JWTHandlerDep,
) -> TokenResponse:
    usuario_repository = SQLAlchemyUsuarioRepository(session)
    use_case = AutenticarUsuarioUseCase(usuario_repository, jwt_handler)
    try:
        resultado = await use_case.execute(form_data.username, form_data.password)
    except CredencialesInvalidasError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    await session.commit()
    return TokenResponse(access_token=resultado.access_token)
