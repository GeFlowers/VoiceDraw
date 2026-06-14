from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


def _read_env_file(path: Path) -> dict[str, str]:
    """读取项目根目录下的 .env 文件，返回简单的键值配置。"""
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        # 跳过空行、注释行以及不符合 KEY=VALUE 格式的内容。
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip("\"'")
    return values


def _as_bool(value: str | bool | None, default: bool) -> bool:
    """把环境变量中的常见布尔写法转换成 bool。"""
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    """后端运行配置，优先来自环境变量，其次来自 .env 文件。"""

    app_env: str = "development"
    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_model: str = "gpt-4o-mini"
    enable_llm: bool = True
    rule_confidence_threshold: float = 0.72
    llm_timeout_seconds: int = 8

    @property
    def llm_ready(self) -> bool:
        """只有显式启用且 API 地址、密钥都存在时才允许调用 LLM。"""
        return self.enable_llm and bool(self.llm_base_url.strip()) and bool(self.llm_api_key.strip())


@lru_cache
def get_settings() -> Settings:
    """构建并缓存 Settings，避免每次请求重复读取配置。"""
    env_file = _read_env_file(Path.cwd() / ".env")

    def get(name: str, default: str = "") -> str:
        # 系统环境变量优先级高于 .env，便于部署环境覆盖本地配置。
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
