from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID

import jwt

from src.domain.exceptions import CredencialesInvalidasError
from src.domain.value_objects.rol import Rol
from src.infrastructure.config import Settings


@dataclass(frozen=True, slots=True)
class TokenPayload:
    sub: UUID
    email: str
    rol: Rol
    exp: datetime


class JWTHandler:
    def __init__(self, settings: Settings) -> None:
        self._secret_key = settings.jwt_secret_key
        self._algorithm = settings.jwt_algorithm
        self._expire_minutes = settings.jwt_access_token_expire_minutes

    def crear_token(self, usuario_id: UUID, email: str, rol: Rol) -> str:
        expira = datetime.now(tz=timezone.utc) + timedelta(minutes=self._expire_minutes)
        payload = {
            "sub": str(usuario_id),
            "email": email,
            "rol": rol.value,
            "exp": expira,
        }
        return jwt.encode(payload, self._secret_key, algorithm=self._algorithm)

    def decodificar_token(self, token: str) -> TokenPayload:
        try:
            data = jwt.decode(token, self._secret_key, algorithms=[self._algorithm])
        except jwt.ExpiredSignatureError as exc:
            raise CredencialesInvalidasError("El token ha expirado") from exc
        except jwt.InvalidTokenError as exc:
            raise CredencialesInvalidasError("Token inválido") from exc

        try:
            return TokenPayload(
                sub=UUID(data["sub"]),
                email=data["email"],
                rol=Rol(data["rol"]),
                exp=datetime.fromtimestamp(data["exp"], tz=timezone.utc),
            )
        except (KeyError, ValueError) as exc:
            raise CredencialesInvalidasError("Token con estructura inválida") from exc
