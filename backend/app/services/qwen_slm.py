import os

from langchain_ollama import ChatOllama

class LocalQwenChatModel(ChatOllama):
    """
    Wrapper around ChatOllama to use the local Qwen 3 8B model.
    Inherits from ChatOllama so it's compatible with LangChain.
    """
    
    def __init__(self, model: str = "qwen3:8b", temperature: float = 0, format: str = ""):
        base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        timeout_seconds = int(os.getenv("OLLAMA_TIMEOUT_SECONDS", "90"))
        super().__init__(
            model=model,
            temperature=temperature,
            format=format,
            base_url=base_url,
            timeout=timeout_seconds,
        )
        
    @property
    def _llm_type(self) -> str:
        return "local-qwen-chat"
