from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging

from app.core.database import Base, engine
from app.core.config import get_settings
from app.api.v1.router import api_router
from app import models  # noqa: F401

settings = get_settings()
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)

app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json"
)

# Set up CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix=settings.API_V1_STR)


logger = logging.getLogger(__name__)


@app.on_event("startup")
def on_startup() -> None:
    settings.upload_dir_path.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(bind=engine)

    logger.info("[startup] llm_backend=%s uploads=%s", settings.LLM_BACKEND, settings.upload_dir_path)
    if (settings.LLM_BACKEND or "").lower() == "mlx":
        logger.info(
            "[startup] mlx base=%s model=%s | chartist base=%s model=%s",
            settings.MLX_BASE_URL,
            settings.MLX_MODEL,
            settings.chartist_base_url,
            settings.chartist_model,
        )
    else:
        logger.info("[startup] ollama base=%s model=%s", settings.OLLAMA_BASE_URL, settings.OLLAMA_MODEL)

    if settings.using_insecure_dev_secrets:
        # These values are committed to the repository, so they are public. Any
        # JWT this process issues can be forged by anyone with the repo, and any
        # stored DB credential can be decrypted. Fine for a local demo only.
        logger.warning(
            "[startup] INSECURE: SECRET_KEY and/or ENCRYPTION_KEY are still the "
            "placeholders committed to this repo. Tokens can be forged and stored "
            "credentials decrypted by anyone with the source. Run `make secrets` "
            "and put the output in backend/.env before exposing this anywhere."
        )


@app.get("/")
def root():
    return {"message": "Welcome to PromptDash API"}


@app.get("/health")
def health() -> dict:
    """Liveness plus the two things that are usually wrong: model and uploads.

    Used by docker-compose's healthcheck and by `make smoke`, so a failure to
    reach the model shows up here instead of inside a chart request.
    """
    backend = (settings.LLM_BACKEND or "ollama").lower()
    return {
        "status": "ok",
        "llm_backend": backend,
        "model": settings.chartist_model if backend == "mlx" else settings.OLLAMA_MODEL,
        "llm_url": settings.chartist_base_url if backend == "mlx" else settings.OLLAMA_BASE_URL,
        "upload_dir": str(settings.upload_dir_path),
        "uploads_present": sorted(
            p.name for p in settings.upload_dir_path.glob("*") if p.suffix.lower() in {".csv", ".xlsx", ".xls"}
        )[:25],
        "insecure_dev_secrets": settings.using_insecure_dev_secrets,
    }
