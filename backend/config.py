from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


def _read_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip("\"'")
    return values


def _as_bool(value: str | bool | None, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    app_env: str = "development"
    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_model: str = "gpt-4o-mini"
    enable_llm: bool = True
    rule_confidence_threshold: float = 0.72
    llm_timeout_seconds: int = 8

    @property
    def llm_ready(self) -> bool:
        return self.enable_llm and bool(self.llm_base_url.strip()) and bool(self.llm_api_key.strip())


@lru_cache
def get_settings() -> Settings:
    env_file = _read_env_file(Path.cwd() / ".env")

    def get(name: str, default: str = "") -> str:
        return os.getenv(name, env_file.get(name, default))

    return Settings(
        app_env=get("APP_ENV", "development"),
        llm_base_url=get("LLM_BASE_URL", ""),
        llm_api_key=get("LLM_API_KEY", ""),
        llm_model=get("LLM_MODEL", "gpt-4o-mini"),
        enable_llm=_as_bool(get("ENABLE_LLM", "true"), True),
        rule_confidence_threshold=float(get("RULE_CONFIDENCE_THRESHOLD", "0.72")),
        llm_timeout_seconds=int(get("LLM_TIMEOUT_SECONDS", "8")),
    )
