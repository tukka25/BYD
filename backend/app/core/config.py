from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    """Application settings."""
    API_V1_STR: str = "/api/v1"
    PROJECT_NAME: str = "PromptDash API"
    MODEL_NAME: str = "qwen:3b-8b"
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "qwen3:8b"
    OLLAMA_TIMEOUT_SECONDS: int = 9000
    # Set to 0 to disable endpoint-level timeout.
    WORKFLOW_TIMEOUT_SECONDS: int = 0

    DATABASE_URL: str = "postgresql+psycopg2://promptdash:promptdash@localhost:5432/promptdash"
    SECRET_KEY: str = "change-me-in-env"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24
    JWT_ALGORITHM: str = "HS256"
    ENCRYPTION_KEY: str = "m3xwSeF4J38MxGfM9Tz11LeG5m8Wz8Y5w6rkaI0sD9A="
    UPLOAD_DIR: str = "backend/uploads"
    ALLOWED_UPLOAD_EXTENSIONS: tuple[str, ...] = (".csv", ".xls", ".xlsx")
    CORS_ORIGINS: list[str] = ["http://localhost:3000"]

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    @property
    def upload_dir_path(self) -> Path:
        return Path(self.UPLOAD_DIR).resolve()

@lru_cache()
def get_settings() -> Settings:
    return Settings()
