import os

from langchain_ollama import ChatOllama
from app.core.config import get_settings

class LocalQwenChatModel(ChatOllama):
    """
    Wrapper around ChatOllama that resolves model/base URL/timeout from settings env vars.
    Inherits from ChatOllama so it's compatible with LangChain.
    """
    
    def __init__(self, model: str | None = None, temperature: float = 0, format: str = ""):
        settings = get_settings()
        base_url = os.getenv("OLLAMA_BASE_URL", settings.OLLAMA_BASE_URL)
        timeout_seconds = int(os.getenv("OLLAMA_TIMEOUT_SECONDS", str(settings.OLLAMA_TIMEOUT_SECONDS)))
        resolved_model = model or os.getenv("OLLAMA_MODEL", settings.OLLAMA_MODEL)
        super().__init__(
            model=resolved_model,
            temperature=temperature,
            format=format,
            base_url=base_url,
            timeout=timeout_seconds,
        )
        
    @property
    def _llm_type(self) -> str:
        return "local-qwen-chat"
