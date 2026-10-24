from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="HISTORIALES_",
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Red de historiales clinicos"
    app_version: str = "0.1.0"
    environment: Literal["desarrollo", "pruebas", "produccion"] = "desarrollo"
    api_prefix: str = "/api/v1"
    cors_origins: list[str] = Field(default_factory=list)
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    postgres_dsn: SecretStr | None = None
    jwt_secret: SecretStr | None = None
    jwt_issuer: str = "historiales-clinicos"
    jwt_audience: str = "historiales-api"
    access_token_minutes: int = Field(default=30, ge=1, le=120)
    mysql_host: str | None = None
    mysql_port: int = Field(default=3307, ge=1, le=65535)
    mysql_user: str = "historiales_app"
    mysql_password: SecretStr | None = None
    mysql_database: str = "hospital_pediatrico"
    mongodb_uri: SecretStr | None = None
    mongodb_database: str = "laboratorio_clinico"
    # Clinica odontologica: clave JSON de la cuenta de servicio de Firebase.
    # Ruta relativa = relativa a la raiz del proyecto. Nunca subir el archivo a Git.
    firestore_credentials: Path | None = None
    firestore_project_id: str | None = None  # opcional: se toma del JSON si se omite
    firestore_database: str = "(default)"
    # Zona horaria de las agendas (dia local de cada cita). Guatemala: UTC-6, sin horario de verano.
    zona_horaria: str = "America/Guatemala"

    @model_validator(mode="after")
    def validar_identidad(self) -> "Settings":
        if bool(self.postgres_dsn) != bool(self.jwt_secret):
            raise ValueError("Configura POSTGRES_DSN y JWT_SECRET juntos.")
        if self.jwt_secret and len(self.jwt_secret.get_secret_value().encode()) < 32:
            raise ValueError("JWT_SECRET debe tener al menos 32 bytes aleatorios.")
        if self.mysql_host and not self.mysql_password:
            raise ValueError("MYSQL_HOST requiere MYSQL_PASSWORD.")
        return self

    @field_validator("firestore_credentials")
    @classmethod
    def resolver_credenciales(cls, value: Path | None) -> Path | None:
        if value is None or str(value).strip() in {"", "."}:
            return None
        return value if value.is_absolute() else PROJECT_ROOT / value

    @field_validator("api_prefix")
    @classmethod
    def validar_prefijo(cls, value: str) -> str:
        if not value.startswith("/") or value == "/" or value.endswith("/"):
            raise ValueError("El prefijo debe comenzar con / y no terminar con /.")
        return value
