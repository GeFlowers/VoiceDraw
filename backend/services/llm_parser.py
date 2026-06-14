from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from backend.config import Settings
from backend.domain.models import CommandPlan, CommandRequest, DrawingOperation, OperationType, PlanSource


class LLMUnavailableError(RuntimeError):
    """LLM 调用失败或返回内容不可用时抛出的统一异常。"""

    pass


# 提供给模型的输出结构示例，用于约束绘图计划字段和取值。
PLAN_SCHEMA_HINT = {
    "operations": [
        {
            "type": "draw_path | draw_shape | add_text | set_style | set_background | select | delete | move | resize | rotate | clear | undo | redo | export | announce | no_op",
            "shape": "line | arrow | rectangle | circle | ellipse | triangle | diamond | pentagon | hexagon | star | heart | flower | cloud | sun | tree | house | mountain | smile | lightning",
            "path": [
                {"command": "M", "x": 0.1, "y": 0.1},
                {"command": "L", "x": 0.9, "y": 0.1},
                {"command": "Q", "x1": 0.6, "y1": 0.2, "x": 0.9, "y": 0.5},
                {"command": "C", "x1": 0.4, "y1": 0.3, "x2": 0.6, "y2": 0.7, "x": 0.8, "y": 0.8},
                {"command": "Z"},
            ],
            "geometry": {"x": 0.5, "y": 0.5, "x2": 0.8, "y2": 0.5, "width": 0.24, "height": 0.18, "radius": 0.1},
            "style": {"stroke": "#111827", "fill": None, "line_width": 4, "opacity": 1, "dashed": False},
            "text": "optional text",
            "value": "optional value",
            "amount": 1.2,
            "delta": {"dx": 0.05, "dy": 0},
            "target": "selected | last | all | none",
            "description": "brief Chinese description",
        }
    ],
    "confidence": 0.0,
    "needs_confirmation": False,
    "spoken_feedback": "简短中文反馈",
    "warnings": [],
}


# 系统提示词要求模型只输出 JSON，并鼓励复杂物体拆成矢量路径组合。
SYSTEM_PROMPT = f"""
你是 Voice Draw 的 AI 命令规划器。你的任务不是做关键词匹配，而是把中文语音指令理解成可执行的矢量绘图计划。

输出要求：
1. 只输出一个 JSON 对象，不要 markdown，不要解释。
2. 坐标全部使用 0 到 1 的归一化画布坐标。
3. 优先使用 draw_path 表达自然物体、复杂轮廓、图标和组合草图；只有圆、矩形、线、箭头等明确几何体才使用 draw_shape。
4. 一个复杂场景要拆成多个操作，例如“画一辆车”应该包含车身、轮子、车窗等多个路径或形状。
5. 操作现有对象时使用 target: selected、last、all 或 none。
6. 无法确定用户意图时返回 no_op，并在 spoken_feedback 里说明需要用户补充什么。
7. 所有颜色必须是 #rrggbb 或 transparent。
8. draw_path 支持 M、L、Q、C、Z 命令。每条路径尽量控制在 4 到 14 个命令内，必要时用多条路径组合。

JSON 结构参考：
{json.dumps(PLAN_SCHEMA_HINT, ensure_ascii=False)}
""".strip()


class LLMCommandParser:
    """调用 OpenAI 兼容的 Chat Completions 接口生成绘图计划。"""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._dependency_error: str | None = None

    @property
    def is_configured(self) -> bool:
        """检查当前配置是否足够发起 LLM 请求。"""
        return self.settings.llm_ready

    def parse(self, request: CommandRequest, normalized_text: str) -> CommandPlan:
        """发送语音上下文到 LLM，并把返回 JSON 转成 CommandPlan。"""
        if not self.is_configured:
            raise LLMUnavailableError("LLM_BASE_URL or LLM_API_KEY is not configured.")

        endpoint = self._completion_url()
        payload = self._build_payload(request, normalized_text)
        started_at = time.perf_counter()
        print(
            f"[voice-draw] ai_api_call_started model={self.settings.llm_model} endpoint={self._redact_endpoint(endpoint)}",
            flush=True,
        )
        try:
            response_data = self._post_json(endpoint, payload)
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:1200]
            if exc.code == 400 and "response_format" in detail:
                # 兼容不支持 response_format 的 OpenAI 风格代理服务。
                payload.pop("response_format", None)
                response_data = self._post_json(endpoint, payload)
            else:
                raise LLMUnavailableError(f"AI API returned HTTP {exc.code}: {detail}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise LLMUnavailableError(f"AI API request failed: {exc}") from exc

        latency_ms = round((time.perf_counter() - started_at) * 1000)
        content = self._extract_message_content(response_data)
        plan_data = self._extract_plan_json(content)
        # 对模型可能输出的驼峰字段、额外字段和缺省字段做一次收敛。
        plan_data = self._normalize_plan_data(plan_data)

        try:
            plan = CommandPlan(**plan_data)
        except Exception as exc:
            raise LLMUnavailableError(f"AI returned an invalid command plan: {exc}") from exc

        metadata = {
            **plan.metadata,
            "llm_attempted": True,
            "llm_model": self.settings.llm_model,
            "llm_latency_ms": latency_ms,
            "planner": "ai_first_vector_planner",
        }
        print(f"[voice-draw] ai_api_call_completed latency_ms={latency_ms}", flush=True)
        return plan.model_copy(update={"source": PlanSource.LLM, "metadata": metadata})

    def _build_payload(self, request: CommandRequest, normalized_text: str) -> dict[str, Any]:
        """组装 Chat Completions 请求体。"""
        user_payload = {
            "transcript": request.transcript,
            "normalized_text": normalized_text,
            "locale": request.locale,
            "canvas_width": request.canvas_width,
            "canvas_height": request.canvas_height,
            "selected_ids": request.selected_ids,
            "recent_object_ids": request.recent_object_ids,
        }
        return {
            "model": self.settings.llm_model,
            "temperature": 0.15,
            # 优先要求模型以 JSON 对象返回，若代理不支持会在 parse 中降级重试。
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
            ],
        }

    def _post_json(self, endpoint: str, payload: dict[str, Any]) -> dict[str, Any]:
        """发送 JSON 请求并确保响应体也是 JSON 对象。"""
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            endpoint,
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {self.settings.llm_api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "VoiceDraw/1.0",
            },
        )
        with urllib.request.urlopen(request, timeout=self.settings.llm_timeout_seconds) as response:
            raw = response.read().decode("utf-8")
        parsed = json.loads(raw)
        if not isinstance(parsed, dict):
            raise LLMUnavailableError("AI API response body is not a JSON object.")
        return parsed

    def _completion_url(self) -> str:
        """把用户配置的 base URL 标准化为 chat/completions endpoint。"""
        base = self.settings.llm_base_url.strip().rstrip("/")
        parsed = urllib.parse.urlparse(base)
        path = parsed.path.rstrip("/")
        if path.endswith("/chat/completions"):
            return base
        if path.endswith("/v1"):
            return f"{base}/chat/completions"
        if path in {"", "/"}:
            return f"{base}/v1/chat/completions"
        return f"{base}/chat/completions"

    @staticmethod
    def _redact_endpoint(endpoint: str) -> str:
        """日志中只保留 endpoint 的协议、域名和路径，避免泄露查询参数。"""
        parsed = urllib.parse.urlparse(endpoint)
        return urllib.parse.urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", ""))

    @staticmethod
    def _extract_message_content(response_data: dict[str, Any]) -> str:
        """兼容普通文本 content 和部分代理返回的 content 列表。"""
        try:
            content = response_data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMUnavailableError("AI API response did not include choices[0].message.content.") from exc
        if isinstance(content, list):
            content = "".join(str(item.get("text", "")) if isinstance(item, dict) else str(item) for item in content)
        if not isinstance(content, str) or not content.strip():
            raise LLMUnavailableError("AI API returned empty content.")
        return content

    @staticmethod
    def _extract_plan_json(content: str) -> dict[str, Any]:
        """从模型文本中提取 JSON 对象，容忍 markdown 代码块包裹。"""
        cleaned = content.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
            cleaned = re.sub(r"\s*```$", "", cleaned)
        try:
            parsed = json.loads(cleaned)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", cleaned, flags=re.S)
            if not match:
                raise LLMUnavailableError("AI content did not contain a JSON object.")
            parsed = json.loads(match.group(0))
        if not isinstance(parsed, dict):
            raise LLMUnavailableError("AI plan is not a JSON object.")
        return parsed

    @staticmethod
    def _normalize_plan_data(plan_data: dict[str, Any]) -> dict[str, Any]:
        """过滤未知字段，并把常见 LLM 输出变体修正为领域模型字段。"""
        allowed_plan_keys = {
            "operations",
            "confidence",
            "needs_confirmation",
            "spoken_feedback",
            "warnings",
            "metadata",
        }
        operations = plan_data.get("operations")
        if not isinstance(operations, list):
            # 没有操作列表时生成 no_op，交给上层展示可理解的失败反馈。
            plan_data["operations"] = [
                DrawingOperation(
                    type=OperationType.NO_OP,
                    description="AI plan did not include operations.",
                ).model_dump()
            ]
            plan_data["confidence"] = 0
            return {key: value for key, value in plan_data.items() if key in allowed_plan_keys}

        normalized_operations: list[dict[str, Any]] = []
        allowed_operation_keys = {
            "type",
            "shape",
            "target",
            "style",
            "geometry",
            "text",
            "value",
            "amount",
            "delta",
            "path",
            "group_id",
            "description",
        }
        for raw_operation in operations:
            if not isinstance(raw_operation, dict):
                continue
            operation = {key: value for key, value in raw_operation.items() if key in allowed_operation_keys}
            style = operation.get("style")
            if isinstance(style, dict) and "lineWidth" in style and "line_width" not in style:
                style["line_width"] = style.pop("lineWidth")
            # 兼容前端或模型常见的 camelCase 动作名。
            if operation.get("type") == "drawPath":
                operation["type"] = "draw_path"
            if operation.get("type") == "addText":
                operation["type"] = "add_text"
            if operation.get("type") == "draw_shape" and operation.get("shape") == "path":
                operation["type"] = "draw_path"
                operation.pop("shape", None)
            normalized_operations.append(operation)
        plan_data["operations"] = normalized_operations
        plan_data.setdefault("confidence", 0.75)
        plan_data.setdefault("needs_confirmation", False)
        plan_data.setdefault("spoken_feedback", "已根据语音生成绘图计划。")
        plan_data.setdefault("warnings", [])
        return {key: value for key, value in plan_data.items() if key in allowed_plan_keys}
