from __future__ import annotations

from backend.app.config import Settings
from backend.app.domain.models import CommandPlan, CommandRequest, DrawingOperation, OperationType, PlanSource


class LLMUnavailableError(RuntimeError):
    pass


class LLMCommandParser:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @property
    def is_configured(self) -> bool:
        return self.settings.llm_ready

    def parse(self, request: CommandRequest, normalized_text: str) -> CommandPlan:
        if not self.is_configured:
            raise LLMUnavailableError("LLM_BASE_URL or LLM_API_KEY is not configured.")

        from langchain_core.output_parsers import PydanticOutputParser
        from langchain_core.prompts import ChatPromptTemplate
        from langchain_openai import ChatOpenAI

        output_parser = PydanticOutputParser(pydantic_object=CommandPlan)
        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "你是语音绘图工具的指令规划器。"
                    "请把中文自然语言绘图指令拆成严格 JSON，字段必须匹配给定 schema。"
                    "坐标使用 0 到 1 的归一化画布坐标。"
                    "常见目标: selected, last, all, none。"
                    "如果无法确认，只返回 no_op 并说明原因。"
                    "\n{format_instructions}",
                ),
                (
                    "human",
                    "用户语音: {transcript}\n"
                    "归一化文本: {normalized_text}\n"
                    "画布尺寸: {canvas_width}x{canvas_height}\n"
                    "已选对象: {selected_ids}\n"
                    "最近对象: {recent_object_ids}",
                ),
            ]
        )
        llm = ChatOpenAI(
            model=self.settings.llm_model,
            api_key=self.settings.llm_api_key,
            base_url=self.settings.llm_base_url,
            temperature=0,
            timeout=self.settings.llm_timeout_seconds,
        )
        chain = prompt | llm | output_parser
        plan = chain.invoke(
            {
                "format_instructions": output_parser.get_format_instructions(),
                "transcript": request.transcript,
                "normalized_text": normalized_text,
                "canvas_width": request.canvas_width,
                "canvas_height": request.canvas_height,
                "selected_ids": request.selected_ids,
                "recent_object_ids": request.recent_object_ids,
            }
        )
        if not isinstance(plan, CommandPlan):
            return CommandPlan(
                operations=[
                    DrawingOperation(
                        type=OperationType.NO_OP,
                        description="LLM returned an invalid plan object.",
                    )
                ],
                confidence=0.0,
                spoken_feedback="AI 指令解析返回了无效结果。",
                warnings=["LLM 输出不是 CommandPlan。"],
                source=PlanSource.LLM,
            )
        return plan.model_copy(update={"source": PlanSource.LLM})
