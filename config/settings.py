from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional


class Settings(BaseSettings):
    # Atlan configuration
    atlan_base_url: str = "https://mock.atlan.com"
    atlan_api_key: str = "mock-atlan-key"
    use_mock_atlan: bool = True

    # LLM configuration
    default_model_provider: str = "mock"  # "mock", "openai", "google", "anthropic"
    openai_api_key: Optional[str] = None
    google_api_key: Optional[str] = None
    anthropic_api_key: Optional[str] = None
    llm_model_id: str = "gpt-4o-mini"

    # Governance & Self-Healing policies
    healing_confidence_threshold: float = 0.80
    auto_apply_healing: bool = True
    log_level: str = "INFO"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )



settings = Settings()
