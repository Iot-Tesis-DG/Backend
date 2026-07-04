from dataclasses import dataclass
from uuid import UUID

from src.domain.value_objects.rol import Rol


@dataclass(slots=True)
class Usuario:
    nombre: str
    email: str
    password_hash: str
    rol: Rol
    id: UUID | None = None

    def tiene_permiso(self, roles_permitidos: tuple[Rol, ...]) -> bool:
        return self.rol in roles_permitidos
