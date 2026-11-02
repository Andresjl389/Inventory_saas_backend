"""Application settings loaded from environment variables."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, PostgresDsn, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # Application
    app_env: Literal["development", "testing", "staging", "production"] = "development"
    app_name: str = "Inventory SaaS"
    debug: bool = False
    api_v1_prefix: str = "/api/v1"

    # Database
    database_url: PostgresDsn
    db_echo: bool = False
    db_pool_size: int = 10
    db_max_overflow: int = 20
    db_pool_recycle: int = 1800

    # Security
    jwt_secret: str = Field(min_length=16)
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 14

    # Cache
    redis_url: str = "redis://localhost:6379/0"

    # CORS
    cors_origins: list[str] = ["http://localhost:3000"]

    # Storage
    # "local" writes under storage_root; "s3" is the same port with a different
    # adapter and is not wired yet.
    storage_backend: Literal["local", "s3"] = "local"
    storage_root: Path = Path("uploads")
    max_upload_size_mb: int = 10
    allowed_upload_types: list[str] = [
        "image/jpeg",
        "image/png",
        "image/webp",
        "image/gif",
        "application/pdf",
        "text/csv",
        "text/plain",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ]

    # Lectura de facturas (OCR).
    # "disabled" por defecto, a propósito: el escaneo está construido y probado
    # pero el modelo queda para cuando el servidor tenga GPU. Así el endpoint
    # responde "no está habilitado" en vez de intentar hablarle a un servidor
    # de inferencia que no existe y fallar con un error de conexión.
    # "local" = nuestro propio modelo (vLLM, llama.cpp, Ollama); es lo que se
    # enciende el día que haya GPU, y son dos variables de entorno.
    # "claude" = la vara de medir, necesita el extra `claude`.
    # "text" = adaptador determinista de las pruebas: ni llave ni red.
    invoice_extractor: Literal["disabled", "local", "claude", "text"] = "disabled"
    invoice_timeout_seconds: float = 180.0

    # Servidor de inferencia propio.
    invoice_local_url: str = "http://localhost:8080/v1"
    invoice_local_model: str = "Qwen/Qwen2.5-VL-7B-Instruct"
    # Solo si pusiste el servidor detrás de una llave; en una red privada no
    # hace falta.
    invoice_local_api_key: str | None = None
    # Forzar la salida al esquema JSON es lo que vuelve usable un modelo de 7B.
    # Bájalo a "json_object" si tu servidor no soporta json_schema.
    invoice_local_json_mode: Literal["json_schema", "json_object", "none"] = "json_schema"
    # El costo de un modelo de visión es por píxel: 1600 px de lado largo deja
    # legible una factura y recorta el trabajo a una fracción.
    invoice_max_image_side: int = 1600
    invoice_max_pages: int = 4

    # La vara de medir (opcional).
    anthropic_api_key: str | None = None
    invoice_model: str = "claude-opus-5-5"
    # Cuántos productos del catálogo se cargan para emparejar los renglones.
    # Una tienda tiene cientos; el tope evita que una empresa grande traiga
    # decenas de miles a memoria en cada escaneo.
    invoice_match_candidates: int = 5000

    s3_endpoint: str | None = None
    s3_bucket: str | None = None
    s3_access_key: str | None = None
    s3_secret_key: str | None = None
    s3_region: str = "us-east-1"

    @field_validator("database_url", mode="before")
    @classmethod
    def _require_async_driver(cls, value: str) -> str:
        """The application runs on asyncpg; fail fast on a sync DSN."""
        if isinstance(value, str) and value.startswith("postgresql://"):
            return value.replace("postgresql://", "postgresql+asyncpg://", 1)
        return value

    @property
    def max_upload_size_bytes(self) -> int:
        return self.max_upload_size_mb * 1024 * 1024

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def sync_database_url(self) -> str:
        """DSN for tooling that cannot use asyncpg (e.g. psql helpers)."""
        return str(self.database_url).replace("postgresql+asyncpg://", "postgresql://", 1)


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]


settings = get_settings()
