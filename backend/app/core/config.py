from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    """Application settings."""
    API_V1_STR: str = "/api/v1"
    PROJECT_NAME: str = "PromptDash API"

    # --- which LLM serves the agents -------------------------------------
    # "ollama" talks to Ollama's /api/chat. "mlx" talks to an OpenAI-compatible
    # server, which is what `mlx_lm server` exposes, and is how the fine-tuned
    # chartist adapter is served on Apple silicon.
    LLM_BACKEND: str = "ollama"

    # One mlx_lm server can host one adapter, so the chartist (fine-tuned) and
    # the planner/detective (base weights) may live on different ports. Leave
    # MLX_CHARTIST_BASE_URL empty to use the same server for everything.
    MLX_BASE_URL: str = "http://localhost:8080/v1"
    MLX_MODEL: str = "qwen3.5-9b-4bit"
    MLX_CHARTIST_BASE_URL: str = ""
    MLX_CHARTIST_MODEL: str = ""
    MLX_API_KEY: str = "not-needed"
    MLX_TIMEOUT_SECONDS: int = 600

    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "qwen3.5:4b"
    OLLAMA_TIMEOUT_SECONDS: int = 9000
    # Set to 0 to disable endpoint-level timeout.
    WORKFLOW_TIMEOUT_SECONDS: int = 0

    DATABASE_URL: str = "postgresql+psycopg2://promptdash:promptdash@localhost:5432/promptdash"
    SECRET_KEY: str = "change-me-in-env"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24
    JWT_ALGORITHM: str = "HS256"
    ENCRYPTION_KEY: str = "m3xwSeF4J38MxGfM9Tz11LeG5m8Wz8Y5w6rkaI0sD9A="
    # Anchored to this file, not the working directory: the old default of
    # "backend/uploads" resolved to backend/backend/uploads whenever uvicorn was
    # started from inside backend/.
    UPLOAD_DIR: str = str(Path(__file__).resolve().parents[2] / "uploads")
    ALLOWED_UPLOAD_EXTENSIONS: tuple[str, ...] = (".csv", ".xls", ".xlsx")
    CORS_ORIGINS: list[str] = ["http://localhost:3000"]

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    @property
    def upload_dir_path(self) -> Path:
        return Path(self.UPLOAD_DIR).resolve()

    @property
    def chartist_base_url(self) -> str:
        """Where the chartist's model lives; falls back to the shared server."""
        return self.MLX_CHARTIST_BASE_URL or self.MLX_BASE_URL

    @property
    def chartist_model(self) -> str:
        return self.MLX_CHARTIST_MODEL or self.MLX_MODEL

    @property
    def using_insecure_dev_secrets(self) -> bool:
        """True while the repo's committed placeholder secrets are still in use.

        Both of these were committed to git, so they are public. Fine for a local
        demo, unsafe for anything else; main.py logs a warning on startup.
        """
        return (
            self.SECRET_KEY in {"change-me-in-env", "replace-with-strong-secret"}
            or self.ENCRYPTION_KEY == "m3xwSeF4J38MxGfM9Tz11LeG5m8Wz8Y5w6rkaI0sD9A="
        )

@lru_cache()
def get_settings() -> Settings:
    return Settings()
