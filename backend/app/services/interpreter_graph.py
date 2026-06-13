from __future__ import annotations

from typing import TypedDict

from backend.app.config import Settings
from backend.app.domain.models import CommandPlan, CommandRequest
from backend.app.services.llm_parser import LLMCommandParser, LLMUnavailableError
from backend.app.services.rule_parser import RuleBasedParser
from backend.app.services.text_normalizer import normalize_text
from backend.app.services.validators import PlanValidator


class InterpreterState(TypedDict, total=False):
    request: CommandRequest
    normalized_text: str
    plan: CommandPlan
    warnings: list[str]


class CommandInterpreter:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.rule_parser = RuleBasedParser()
        self.llm_parser = LLMCommandParser(settings)
        self.validator = PlanValidator()
        self.graph = self._build_graph()

    def interpret(self, request: CommandRequest) -> CommandPlan:
        result = self.graph.invoke({"request": request, "warnings": []})
        return result["plan"]

    def _build_graph(self):
        from langgraph.graph import END, StateGraph

        graph = StateGraph(InterpreterState)
        graph.add_node("normalize", self._normalize)
        graph.add_node("rule_parse", self._rule_parse)
        graph.add_node("llm_parse", self._llm_parse)
        graph.add_node("validate", self._validate)

        graph.set_entry_point("normalize")
        graph.add_edge("normalize", "rule_parse")
        graph.add_conditional_edges(
            "rule_parse",
            self._route_after_rule_parse,
            {
                "llm_parse": "llm_parse",
                "validate": "validate",
            },
        )
        graph.add_edge("llm_parse", "validate")
        graph.add_edge("validate", END)
        return graph.compile()

    def _normalize(self, state: InterpreterState) -> InterpreterState:
        request = state["request"]
        return {**state, "normalized_text": normalize_text(request.transcript)}

    def _rule_parse(self, state: InterpreterState) -> InterpreterState:
        plan = self.rule_parser.parse(state["request"])
        return {**state, "plan": plan}

    def _route_after_rule_parse(self, state: InterpreterState) -> str:
        plan = state["plan"]
        if plan.confidence < self.settings.rule_confidence_threshold and self.llm_parser.is_configured:
            return "llm_parse"
        return "validate"

    def _llm_parse(self, state: InterpreterState) -> InterpreterState:
        try:
            plan = self.llm_parser.parse(state["request"], state["normalized_text"])
            return {**state, "plan": plan}
        except (LLMUnavailableError, Exception) as exc:
            plan = state["plan"]
            warnings = [*plan.warnings, f"LLM 解析不可用，已使用规则解析结果: {exc}"]
            return {**state, "plan": plan.model_copy(update={"warnings": warnings})}

    def _validate(self, state: InterpreterState) -> InterpreterState:
        return {**state, "plan": self.validator.validate(state["plan"])}
