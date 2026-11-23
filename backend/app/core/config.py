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

    # Only for the side-by-side comparison against the local model. Nothing in
    # the normal request path reads this, so the product still runs with no key
    # and nothing leaves the machine unless a comparison is explicitly run.
    CLAUDE_API_KEY: str = ""
    ANTHROPIC_API_KEY: str = ""
    CLAUDE_EFFORT: str = "medium"

    # One mlx_lm server can host one adapter, so the chartist (fine-tuned) and
    # the planner/detective (base weights) may live on different ports. Leave
    # MLX_CHARTIST_BASE_URL empty to use the same server for everything.
    MLX_BASE_URL: str = "http://localhost:8080/v1"
    # MUST be the literal "default_model" to get the fine-tuned adapter.
    # mlx_lm server registers its --adapter-path under exactly that key
    # (server.py: _adapter_map["default_model"] = cli_args.adapter_path) and then
    # looks the adapter up BY MODEL ID. Any other id -- including the real model
    # path -- loads the base weights with no adapter, and a HuggingFace repo id
    # makes the server download that model instead. Measured difference on one
    # chartist request: "default_model" returned valid Plotly in 15s and 186
    # tokens; the repo id rambled for 1024 tokens, hit the token cap, and
    # returned content=None.
    MLX_MODEL: str = "default_model"
    MLX_CHARTIST_BASE_URL: str = ""
    MLX_CHARTIST_MODEL: str = ""
    MLX_API_KEY: str = "not-needed"
    MLX_TIMEOUT_SECONDS: int = 600

    # Whether the planner's chart type is actually sent to the chartist, and in
    # which form: "off", "inline" or "directive". See `chart_type_hint` in
    # agents/chartist_contract.py for the exact text each one produces, and
    # chartist-finetune/ab_planner_hint.py for the measurement behind the
    # default. Only turn this on for a model trained with the same hint shape:
    # lora-v1 saw bare questions, so a hint is a prompt it never trained on.
    CHARTIST_CHART_TYPE_HINT: str = "off"
    # "ai": the dashboard is planned by the analyst and planner models and checked
    # by code (agents/dashboard_flow.py). "rules": the old name-based architect,
    # kept only as a switch to roll back to.
    DASHBOARD_PLANNER: str = "ai"
    # "on": before a dashboard is planned, an explorer call checks facts about the
    # data with bounded tools (agents/data_tools.py, agents/discovery.py), and
    # every final chart plan is checked against the real data. "planner": no
    # explorer; the planner itself may call preview_chart, row_grain,
    # inspect_column, find_columns and relationship (at most 3 calls) before its
    # JSON, and the same data check runs. "off": neither. "on" by the no-harm
    # rule on the first 40 frozen planning rows (chartist-finetune/measure_planning_tools.py,
    # AGENTS.md); docker compose passes it through as ${PLANNER_TOOLS:-on}.
    PLANNER_TOOLS: str = "on"

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

    @property
    def claude_api_key(self) -> str:
        """Either spelling; the SDK's own variable wins if both are set."""
        return self.ANTHROPIC_API_KEY or self.CLAUDE_API_KEY

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

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
