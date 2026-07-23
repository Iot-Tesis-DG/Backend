from functools import lru_cache
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_SECRETO_POR_DEFECTO = "clave_secreta_larga_y_aleatoria_cambiar_en_produccion"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql+asyncpg://user:pass@localhost:5432/farmacia_db"

    jwt_secret_key: str = _SECRETO_POR_DEFECTO
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 60
    jwt_issuer: str = "cadena-frio-backend"
    jwt_audience: str = "cadena-frio-api"

    # Tickets efímeros para autenticar el stream SSE (EventSource no envía
    # el header Authorization, así que se emite un JWT de un solo propósito).
    sse_ticket_expire_seconds: int = 60

    # Límite de intentos de login por IP dentro de la ventana deslizante.
    login_max_intentos: int = 5
    login_ventana_segundos: int = 300

    # Límite global de solicitudes por IP (protección DoS de capa aplicación,
    # OWASP API4). /health queda exento para los probes de la plataforma.
    api_rate_limit_habilitado: bool = True
    api_rate_limit_max_solicitudes: int = 240
    api_rate_limit_ventana_segundos: int = 60
    security_state_max_entries: int = 10_000

    # Tamaño máximo del cuerpo de una request (payloads IoT y formularios son
    # pequeños; cualquier cosa mayor es anómala).
    max_body_bytes: int = 64 * 1024

    # Mínimo privilegio de dispositivos: en estricto, solo device_id
    # provisionados en la tabla `devices` pueden registrar lecturas.
    device_registry_estricto: bool = True

    # Hosts permitidos en producción (mitiga ataques por header Host).
    allowed_hosts: list[str] = []

    password_min_length: int = 10

    cors_origins: list[str] = ["http://localhost:5173"]

    mqtt_host: str = "tu-instancia.emqx.cloud"
    mqtt_port: int = 8883
    mqtt_username: str = "backend_service"
    mqtt_password: str = "token_seguro"
    mqtt_client_id: str = "backend-farmacia-cdl"
    mqtt_tls_enabled: bool = True
    mqtt_enabled: bool = True

    # Solo se aceptan entornos con semántica de seguridad conocida. Un valor
    # como "prod" no debe omitir silenciosamente los controles de production.
    environment: Literal["development", "test", "production"] = "development"

    @model_validator(mode="after")
    def _validar_secretos_en_produccion(self) -> "Settings":
        if self.environment == "production":
            if self.jwt_secret_key == _SECRETO_POR_DEFECTO or len(self.jwt_secret_key) < 32:
                raise ValueError(
                    "JWT_SECRET_KEY debe ser un secreto aleatorio de al menos 32 caracteres "
                    "en producción (no usar el valor por defecto)."
                )
            if any(origen == "*" for origen in self.cors_origins):
                raise ValueError("CORS_ORIGINS no puede contener '*' en producción.")
            if not self.allowed_hosts:
                raise ValueError(
                    "ALLOWED_HOSTS debe declararse explícitamente en producción."
                )
            if self.database_url == "postgresql+asyncpg://user:pass@localhost:5432/farmacia_db":
                raise ValueError("DATABASE_URL no puede usar el valor de ejemplo en producción.")
            if not self.cors_origins or any(
                not origen.startswith("https://") for origen in self.cors_origins
            ):
                raise ValueError("CORS_ORIGINS debe declarar únicamente orígenes HTTPS en producción.")
            if self.mqtt_enabled:
                # RNF-05: transmisión sobre TLS y credenciales fuera del código fuente.
                if not self.mqtt_tls_enabled:
                    raise ValueError("MQTT_TLS_ENABLED debe ser true en producción (RNF-05).")
                if self.mqtt_password in ("token_seguro", ""):
                    raise ValueError(
                        "MQTT_PASSWORD no puede ser el valor por defecto en producción (RNF-05)."
                    )
                if self.mqtt_host == "tu-instancia.emqx.cloud":
                    raise ValueError("MQTT_HOST no puede usar el valor de ejemplo en producción.")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
