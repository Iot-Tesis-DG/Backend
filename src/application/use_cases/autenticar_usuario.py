from dataclasses import dataclass

from src.domain.exceptions import CredencialesInvalidasError
from src.domain.repositories.i_usuario_repository import IUsuarioRepository
from src.infrastructure.security.jwt_handler import JWTHandler
from src.infrastructure.security.password_hasher import verify_password


@dataclass(frozen=True, slots=True)
class ResultadoAutenticacion:
    access_token: str
    token_type: str = "bearer"


class AutenticarUsuarioUseCase:
    """RF-17: autenticación JWT (login) previa a la autorización RBAC."""

    def __init__(self, usuario_repository: IUsuarioRepository, jwt_handler: JWTHandler) -> None:
        self._usuario_repository = usuario_repository
        self._jwt_handler = jwt_handler

    async def execute(self, email: str, password: str) -> ResultadoAutenticacion:
        usuario = await self._usuario_repository.obtener_por_email(email)
        if usuario is None or not verify_password(password, usuario.password_hash):
            raise CredencialesInvalidasError("Email o contraseña incorrectos")

        token = self._jwt_handler.crear_token(usuario.id, usuario.email, usuario.rol)
        return ResultadoAutenticacion(access_token=token)
