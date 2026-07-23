from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

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
    jti: str


@dataclass(frozen=True, slots=True)
class TicketSSE:
    usuario_id: UUID
    jti: str
    exp: datetime


class JWTHandler:
    def __init__(self, settings: Settings) -> None:
        self._secret_key = settings.jwt_secret_key
        self._algorithm = settings.jwt_algorithm
        self._expire_minutes = settings.jwt_access_token_expire_minutes
        self._issuer = settings.jwt_issuer
        self._audience = settings.jwt_audience
        self._sse_audience = f"{settings.jwt_audience}:sse"
        self._sse_ticket_expire_seconds = settings.sse_ticket_expire_seconds

    def crear_token(self, usuario_id: UUID, email: str, rol: Rol) -> str:
        ahora = datetime.now(tz=timezone.utc)
        payload = {
            "sub": str(usuario_id),
            "email": email,
            "rol": rol.value,
            "iat": ahora,
            "exp": ahora + timedelta(minutes=self._expire_minutes),
            "iss": self._issuer,
            "aud": self._audience,
            # jti único: distingue tokens entre sí y habilita revocación futura.
            "jti": uuid4().hex,
        }
        return jwt.encode(payload, self._secret_key, algorithm=self._algorithm)

    def decodificar_token(self, token: str) -> TokenPayload:
        try:
            data = jwt.decode(
                token,
                self._secret_key,
                algorithms=[self._algorithm],
                audience=self._audience,
                issuer=self._issuer,
                options={"require": ["exp", "iat", "sub", "iss", "aud", "jti"]},
            )
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
                jti=data["jti"],
            )
        except (KeyError, ValueError) as exc:
            raise CredencialesInvalidasError("Token con estructura inválida") from exc

    def crear_ticket_sse(self, usuario_id: UUID) -> str:
        """Ticket efímero de un solo propósito para abrir el stream SSE.

        EventSource no puede enviar el header Authorization; el ticket viaja
        como query param, por lo que su vida corta (segundos) limita la
        exposición si queda registrado en logs intermedios.
        """
        ahora = datetime.now(tz=timezone.utc)
        payload = {
            "sub": str(usuario_id),
            "iat": ahora,
            "exp": ahora + timedelta(seconds=self._sse_ticket_expire_seconds),
            "iss": self._issuer,
            "aud": self._sse_audience,
            "jti": uuid4().hex,
        }
        return jwt.encode(payload, self._secret_key, algorithm=self._algorithm)

    def validar_ticket_sse(self, ticket: str) -> TicketSSE:
        """Valida el ticket y devuelve sus datos; el consumo de un solo uso
        (por jti) lo aplica la capa de interface con un JtiStore."""
        try:
            data = jwt.decode(
                ticket,
                self._secret_key,
                algorithms=[self._algorithm],
                audience=self._sse_audience,
                issuer=self._issuer,
                options={"require": ["exp", "iat", "sub", "iss", "aud", "jti"]},
            )
            return TicketSSE(
                usuario_id=UUID(data["sub"]),
                jti=data["jti"],
                exp=datetime.fromtimestamp(data["exp"], tz=timezone.utc),
            )
        except (jwt.InvalidTokenError, ValueError) as exc:
            raise CredencialesInvalidasError("Ticket SSE inválido o expirado") from exc
