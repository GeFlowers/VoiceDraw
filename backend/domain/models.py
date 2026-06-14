from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class OperationType(str, Enum):
    """前端画布能够执行的动作类型。"""

    DRAW_SHAPE = "draw_shape"
    DRAW_PATH = "draw_path"
    ADD_TEXT = "add_text"
    SET_STYLE = "set_style"
    SET_BACKGROUND = "set_background"
    SELECT = "select"
    DELETE = "delete"
    MOVE = "move"
    RESIZE = "resize"
    ROTATE = "rotate"
    CLEAR = "clear"
    UNDO = "undo"
    REDO = "redo"
    EXPORT = "export"
    ANNOUNCE = "announce"
    NO_OP = "no_op"


class ShapeType(str, Enum):
    """后端计划中支持的图形类型。"""

    PATH = "path"
    LINE = "line"
    ARROW = "arrow"
    RECTANGLE = "rectangle"
    CIRCLE = "circle"
    ELLIPSE = "ellipse"
    TRIANGLE = "triangle"
    DIAMOND = "diamond"
    PENTAGON = "pentagon"
    HEXAGON = "hexagon"
    STAR = "star"
    HEART = "heart"
    FLOWER = "flower"
    CLOUD = "cloud"
    SUN = "sun"
    TREE = "tree"
    HOUSE = "house"
    MOUNTAIN = "mountain"
    SMILE = "smile"
    LIGHTNING = "lightning"
    TEXT = "text"


class PlanSource(str, Enum):
    """标记绘图计划来自规则解析、LLM，还是经过修复后的结果。"""

    RULE = "rule"
    LLM = "llm"
    REPAIRED = "repaired"


# 操作对象选择器，和前端画布的选中态约定保持一致。
TargetSelector = Literal["selected", "last", "all", "none"]


class VoiceDrawModel(BaseModel):
    """项目领域模型基类，使用 Pydantic 负责校验、复制和序列化。"""

    model_config = ConfigDict()

    def model_dump(self, **kwargs: Any) -> dict[str, Any]:
        """默认输出 JSON 友好的 dict，保持原 API 调用方式不变。"""
        kwargs.setdefault("mode", "json")
        return super().model_dump(**kwargs)


def _clamp(value: float, min_value: float, max_value: float) -> float:
    """把数值限制在前后端共同约定的安全范围内。"""
    return max(min_value, min(max_value, value))


class DrawingStyle(VoiceDrawModel):
    """单个绘图动作使用的描边、填充和透明度样式。"""

    stroke: str | None = "#1f2937"
    fill: str | None = None
    line_width: float = 4.0
    opacity: float = 1.0
    dashed: bool = False

    @field_validator("stroke", "fill")
    @classmethod
    def _normalize_color(cls, value: str | None) -> str | None:
        """只接受短/长十六进制颜色，透明填充用 None 表示。"""
        if value is None:
            return None
        if not isinstance(value, str) or not value.startswith("#") or len(value) not in {4, 7}:
            raise ValueError("color must be a hex value such as #ff0000")
        return value.lower()

    @field_validator("line_width")
    @classmethod
    def _clamp_line_width(cls, value: float) -> float:
        """线宽限制在前端可稳定渲染的范围内。"""
        return _clamp(float(value), 0.5, 48.0)

    @field_validator("opacity")
    @classmethod
    def _clamp_opacity(cls, value: float) -> float:
        """透明度限制在可见范围内。"""
        return _clamp(float(value), 0.05, 1.0)


class Geometry(VoiceDrawModel):
    """归一化画布坐标和尺寸，所有值按 0 到 1 表示。"""

    x: float | None = None
    y: float | None = None
    x2: float | None = None
    y2: float | None = None
    width: float | None = None
    height: float | None = None
    radius: float | None = None

    @field_validator("x", "y", "x2", "y2")
    @classmethod
    def _clamp_coordinate(cls, value: float | None) -> float | None:
        """坐标在入模时裁剪，防止 LLM 或规则解析返回越界值。"""
        return None if value is None else _clamp(float(value), 0.0, 1.0)

    @field_validator("width", "height")
    @classmethod
    def _clamp_size(cls, value: float | None) -> float | None:
        """尺寸需要保留最小可见值。"""
        return None if value is None else _clamp(float(value), 0.01, 1.0)

    @field_validator("radius")
    @classmethod
    def _clamp_radius(cls, value: float | None) -> float | None:
        """半径限制在画布相对尺寸范围内。"""
        return None if value is None else _clamp(float(value), 0.01, 0.6)


class PathCommand(VoiceDrawModel):
    """矢量路径中的单条绘制指令。"""

    command: str
    x: float | None = None
    y: float | None = None
    x1: float | None = None
    y1: float | None = None
    x2: float | None = None
    y2: float | None = None

    @field_validator("command")
    @classmethod
    def _normalize_command(cls, value: str) -> str:
        """前端只实现了这五类路径命令，其他命令在模型层直接拒绝。"""
        command = str(value).upper()
        if command not in {"M", "L", "Q", "C", "Z"}:
            raise ValueError("path command must be one of M, L, Q, C, Z")
        return command

    @field_validator("x", "y", "x1", "y1", "x2", "y2")
    @classmethod
    def _clamp_coordinate(cls, value: float | None) -> float | None:
        """路径坐标使用归一化画布坐标。"""
        return None if value is None else _clamp(float(value), 0.0, 1.0)


class Vector(VoiceDrawModel):
    """移动操作使用的二维偏移量。"""

    dx: float = 0
    dy: float = 0

    @field_validator("dx", "dy")
    @classmethod
    def _clamp_delta(cls, value: float) -> float:
        """偏移量同样使用归一化坐标，限制在单个画布范围内。"""
        return _clamp(float(value), -1.0, 1.0)


class DrawingOperation(VoiceDrawModel):
    """一条可执行的画布操作，是后端传给前端的最小动作单位。"""

    type: OperationType
    shape: ShapeType | None = None
    target: TargetSelector | None = None
    style: DrawingStyle | None = None
    geometry: Geometry | None = None
    text: str | None = None
    value: str | None = None
    amount: float | None = None
    delta: Vector | None = None
    path: list[PathCommand] | None = None
    group_id: str | None = None
    description: str = ""


class CommandRequest(VoiceDrawModel):
    """前端提交的语音命令请求。"""

    transcript: str
    locale: str = "zh-CN"
    canvas_width: int = 1280
    canvas_height: int = 720
    selected_ids: list[str] = Field(default_factory=list)
    recent_object_ids: list[str] = Field(default_factory=list)

    @field_validator("transcript")
    @classmethod
    def _normalize_transcript(cls, value: str) -> str:
        """请求边界处做轻量清洗，避免空文本进入解析器。"""
        transcript = str(value).strip()
        if not transcript:
            raise ValueError("transcript is required")
        return transcript[:2000]

    @field_validator("locale")
    @classmethod
    def _normalize_locale(cls, value: str | None) -> str:
        """缺省语言环境保持中文。"""
        return str(value or "zh-CN")

    @field_validator("canvas_width", "canvas_height")
    @classmethod
    def _clamp_canvas_size(cls, value: int) -> int:
        """限制异常画布尺寸进入解析器。"""
        return max(100, min(10000, int(value)))

    @field_validator("selected_ids", "recent_object_ids")
    @classmethod
    def _normalize_ids(cls, value: list[Any]) -> list[str]:
        """对象 id 统一转成字符串，便于前后端比较。"""
        return [str(item) for item in value]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CommandRequest:
        """从 HTTP JSON 对象构造请求模型，并补齐默认值。"""
        return cls(
            transcript=data.get("transcript", ""),
            locale=data.get("locale", "zh-CN"),
            canvas_width=data.get("canvas_width", 1280),
            canvas_height=data.get("canvas_height", 720),
            selected_ids=data.get("selected_ids") or [],
            recent_object_ids=data.get("recent_object_ids") or [],
        )


class CommandPlan(VoiceDrawModel):
    """完整的命令解释结果，包含动作列表、置信度和给用户的反馈。"""

    operations: list[DrawingOperation] = Field(default_factory=list)
    confidence: float = 0.0
    needs_confirmation: bool = False
    spoken_feedback: str = ""
    warnings: list[str] = Field(default_factory=list)
    source: PlanSource = PlanSource.RULE
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("confidence")
    @classmethod
    def _clamp_confidence(cls, value: float) -> float:
        """统一修正置信度范围，便于 API 响应稳定输出。"""
        return _clamp(float(value), 0.0, 1.0)

    @field_validator("warnings")
    @classmethod
    def _normalize_warnings(cls, value: list[Any]) -> list[str]:
        """警告信息统一转成字符串。"""
        return [str(item) for item in value]

    @field_validator("metadata")
    @classmethod
    def _normalize_metadata(cls, value: dict[str, Any] | None) -> dict[str, Any]:
        """确保 metadata 始终是可扩展字典。"""
        return dict(value or {})
