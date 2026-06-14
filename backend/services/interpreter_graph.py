from __future__ import annotations

from backend.config import Settings
from backend.domain.models import CommandPlan, CommandRequest
from backend.services.llm_parser import LLMCommandParser, LLMUnavailableError
from backend.services.validators import PlanValidator


class CommandInterpreter:
    """命令解释编排器，只负责 AI 规划和计划校验。"""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.llm_parser = LLMCommandParser(settings)
        self.validator = PlanValidator()

    def interpret(self, request: CommandRequest) -> CommandPlan:
        """调用 AI 生成矢量计划；AI 不可用时直接报错。"""
        if not self.llm_parser.is_configured:
            raise LLMUnavailableError("AI API 尚未配置，请检查 LLM_BASE_URL 和 LLM_API_KEY。")
        return self.validator.validate(self.llm_parser.parse(request))
