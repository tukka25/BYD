from pydantic_settings import BaseSettings
from functools import lru_cache

class Settings(BaseSettings):
    """Application settings."""
    API_V1_STR: str = "/api/v1"
    PROJECT_NAME: str = "PromptDash API"
    # Assuming local execution or mocked for now
    MODEL_NAME: str = "qwen:3b-8b" 

    class Config:
        env_file = ".env"

@lru_cache()
def get_settings() -> Settings:
    return Settings()
