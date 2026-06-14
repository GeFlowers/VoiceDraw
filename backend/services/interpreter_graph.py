from __future__ import annotations

from backend.config import Settings
from backend.domain.models import CommandPlan, CommandRequest, DrawingOperation, OperationType, PlanSource
from backend.services.llm_parser import LLMCommandParser, LLMUnavailableError
from backend.services.rule_parser import RuleBasedParser
from backend.services.text_normalizer import normalize_text
from backend.services.validators import PlanValidator


class CommandInterpreter:
    """命令解释编排器，负责在 LLM、规则兜底和计划校验之间串联流程。"""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.rule_parser = RuleBasedParser()
        self.llm_parser = LLMCommandParser(settings)
        self.validator = PlanValidator()

    def interpret(self, request: CommandRequest) -> CommandPlan:
        """优先调用 LLM 生成矢量计划，失败时退回本地规则解析。"""
        normalized_text = normalize_text(request.transcript)
        if self.llm_parser.is_configured:
            try:
                # LLM 返回的计划也必须经过统一校验，避免前端收到非法动作。
                return self.validator.validate(self.llm_parser.parse(request, normalized_text))
            except (LLMUnavailableError, Exception) as exc:
                # AI 服务不可用时保留错误信息，并使用规则解析保障基本可用性。
                fallback = self.rule_parser.parse(request)
                metadata = {
                    **fallback.metadata,
                    "llm_attempted": True,
                    "llm_error": str(exc),
                    "planner": "rule_fallback_after_ai_error",
                }
                warnings = [*fallback.warnings, f"AI API 调用失败，已临时使用本地兜底: {exc}"]
                return self.validator.validate(
                    fallback.model_copy(
                        update={
                            "source": PlanSource.REPAIRED,
                            "warnings": warnings,
                            "metadata": metadata,
                        }
                    )
                )

        # 当前产品策略要求 AI 可用时才执行语音绘图，避免静默使用低置信规则结果。
        plan = CommandPlan(
            operations=[
                DrawingOperation(
                    type=OperationType.NO_OP,
                    description="AI API is not configured.",
                )
            ],
            confidence=0.0,
            needs_confirmation=True,
            spoken_feedback="AI API 尚未配置，无法执行语音画图。请检查 LLM_BASE_URL 和 LLM_API_KEY。",
            warnings=["LLM_BASE_URL 或 LLM_API_KEY 未配置，已阻止静默规则解析。"],
            source=PlanSource.REPAIRED,
            metadata={"llm_attempted": False, "planner": "ai_required"},
        )
        return self.validator.validate(plan)
