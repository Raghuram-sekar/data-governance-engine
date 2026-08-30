import os
import urllib.request
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

# Ensure .env is loaded into os.environ
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

from config.settings import settings


def is_ollama_alive() -> bool:
    """Checks if Ollama server is responding on localhost:11434."""
    try:
        req = urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=0.2)
        return req.getcode() == 200
    except Exception:
        return False


def get_agno_model():
    """
    Returns the configured LLM model for Agno Agents.
    Defaults to Local Ollama (llama3.2:1b) running on GPU for unlimited free inference.
    If Ollama is not running, falls back safely to deterministic reasoning engine.
    """
    os.environ.pop("GEMINI_API_KEY", None)

    provider = os.getenv("LLM_PROVIDER", "").lower() or settings.default_model_provider.lower()

    if provider == "ollama":
        if is_ollama_alive():
            try:
                from agno.models.ollama import Ollama
                model_name = os.getenv("OLLAMA_MODEL", "llama3.2:1b")
                return Ollama(id=model_name)
            except Exception:
                pass
        # If Ollama is not responding, return None so healers use deterministic semantic reasoning safely
        return None

    api_key = settings.google_api_key or os.getenv("GOOGLE_API_KEY")
    if api_key and not api_key.startswith("your_"):
        os.environ["GOOGLE_API_KEY"] = api_key
        try:
            from agno.models.google import Gemini
            model_id = settings.llm_model_id if ("gemini" in settings.llm_model_id and settings.llm_model_id != "gemini-2.0-flash") else "gemini-3.5-flash-lite"
            return Gemini(id=model_id, api_key=api_key)
        except Exception:
            pass

    if settings.openai_api_key or os.getenv("OPENAI_API_KEY"):
        openai_key = settings.openai_api_key or os.getenv("OPENAI_API_KEY")
        if openai_key and not openai_key.startswith("your_"):
            from agno.models.openai import OpenAIChat
            return OpenAIChat(id=settings.llm_model_id or "gpt-4o-mini", api_key=openai_key)

    return None
