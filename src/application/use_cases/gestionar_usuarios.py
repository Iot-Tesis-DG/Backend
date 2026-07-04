from src.domain.entities.usuario import Usuario
from src.domain.exceptions import DomainError
from src.domain.repositories.i_usuario_repository import IUsuarioRepository
from src.domain.value_objects.rol import Rol
from src.infrastructure.security.password_hasher import hash_password


class CrearUsuarioUseCase:
    """RF-17: gestión de usuarios y roles (RBAC) restringida al administrador."""

    def __init__(self, usuario_repository: IUsuarioRepository) -> None:
        self._usuario_repository = usuario_repository

    async def execute(self, nombre: str, email: str, password: str, rol: Rol) -> Usuario:
        existente = await self._usuario_repository.obtener_por_email(email)
        if existente is not None:
            raise DomainError(f"Ya existe un usuario con el email {email}")

        usuario = Usuario(nombre=nombre, email=email, password_hash=hash_password(password), rol=rol)
        return await self._usuario_repository.agregar(usuario)


class ListarUsuariosUseCase:
    def __init__(self, usuario_repository: IUsuarioRepository) -> None:
        self._usuario_repository = usuario_repository

    async def execute(self) -> list[Usuario]:
        return await self._usuario_repository.listar()
