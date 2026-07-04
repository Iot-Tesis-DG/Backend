from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql+asyncpg://user:pass@localhost:5432/farmacia_db"

    jwt_secret_key: str = "clave_secreta_larga_y_aleatoria_cambiar_en_produccion"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 60

    mqtt_host: str = "tu-instancia.emqx.cloud"
    mqtt_port: int = 8883
    mqtt_username: str = "backend_service"
    mqtt_password: str = "token_seguro"
    mqtt_client_id: str = "backend-farmacia-cdl"
    mqtt_tls_enabled: bool = True
    mqtt_enabled: bool = True

    environment: str = "development"


@lru_cache
def get_settings() -> Settings:
    return Settings()
