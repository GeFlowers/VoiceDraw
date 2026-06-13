from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "development"
    llm_base_url: str = Field(default="", alias="LLM_BASE_URL")
    llm_api_key: str = Field(default="", alias="LLM_API_KEY")
    llm_model: str = Field(default="gpt-4o-mini", alias="LLM_MODEL")
    enable_llm: bool = Field(default=True, alias="ENABLE_LLM")
    rule_confidence_threshold: float = Field(default=0.72, alias="RULE_CONFIDENCE_THRESHOLD")
    llm_timeout_seconds: int = Field(default=8, alias="LLM_TIMEOUT_SECONDS")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    @property
    def llm_ready(self) -> bool:
        return self.enable_llm and bool(self.llm_base_url.strip()) and bool(self.llm_api_key.strip())


@lru_cache
def get_settings() -> Settings:
    return Settings()
