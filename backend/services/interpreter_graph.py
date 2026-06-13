from __future__ import annotations

from backend.config import Settings
from backend.domain.models import CommandPlan, CommandRequest
from backend.services.llm_parser import LLMCommandParser, LLMUnavailableError
from backend.services.rule_parser import RuleBasedParser
from backend.services.text_normalizer import normalize_text
from backend.services.validators import PlanValidator


class CommandInterpreter:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.rule_parser = RuleBasedParser()
        self.llm_parser = LLMCommandParser(settings)
        self.validator = PlanValidator()

    def interpret(self, request: CommandRequest) -> CommandPlan:
        normalized_text = normalize_text(request.transcript)
        plan = self.rule_parser.parse(request)

        if plan.confidence < self.settings.rule_confidence_threshold and self.llm_parser.is_configured:
            try:
                plan = self.llm_parser.parse(request, normalized_text)
            except (LLMUnavailableError, Exception) as exc:
                warnings = [*plan.warnings, f"LLM unavailable, using rule result: {exc}"]
                plan = plan.model_copy(update={"warnings": warnings})

        return self.validator.validate(plan)
