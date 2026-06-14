from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.config import Settings, get_settings
from backend.llm_parser import LLMCommandParser, LLMUnavailableError
from backend.models import CommandPlan, CommandRequest
from backend.validators import PlanValidator


logger = logging.getLogger(__name__)


class CommandInterpreter:
    """命令解释编排器，只负责 AI 规划和计划校验。"""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.llm_parser = LLMCommandParser(settings)
        self.validator = PlanValidator()

    def interpret(self, request: CommandRequest) -> CommandPlan:
        """调用 AI 生成矢量计划，AI 不可用时直接报错。"""
        if not self.llm_parser.is_configured:
            raise LLMUnavailableError("AI API 尚未配置，请检查 LLM_BASE_URL 和 LLM_API_KEY。")
        return self.validator.validate(self.llm_parser.parse(request))


def create_app(settings: Settings | None = None) -> FastAPI:
    """创建 FastAPI 应用，提供 API 路由并托管前端静态资源。"""
    resolved_settings = settings or get_settings()
    interpreter = CommandInterpreter(resolved_settings)
    project_root = Path(__file__).parent.parent
    static_dir = project_root / "frontend"

    app = FastAPI(title="VoiceDraw API")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/health")
    async def health() -> dict[str, Any]:
        """返回服务和 AI 配置状态。"""
        return {
            "status": "ok",
            "env": resolved_settings.app_env,
            "llm_ready": interpreter.llm_parser.is_configured,
            "llm_model": resolved_settings.llm_model,
            "llm_model_chain": list(resolved_settings.llm_model_chain),
            "planner_mode": "ai_enum_vector_planner",
        }

    @app.post("/api/commands/interpret", response_model=CommandPlan)
    async def interpret_command(request: CommandRequest) -> CommandPlan:
        """把语音识别文本转换成前端可执行的绘图计划。"""
        try:
            return interpreter.interpret(request)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except LLMUnavailableError as exc:
            logger.warning("LLM command interpretation failed: %s", exc)
            raise HTTPException(status_code=502, detail="AI 服务暂时不可用，请稍后重试。") from exc
        except Exception as exc:
            logger.exception("Unexpected command interpretation error")
            raise HTTPException(status_code=500, detail="服务器处理指令时发生错误。") from exc

    app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")
    return app


app = create_app()
