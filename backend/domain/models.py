from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field, fields, is_dataclass
from enum import Enum
from typing import Any, Literal


class OperationType(str, Enum):
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
    RULE = "rule"
    LLM = "llm"
    REPAIRED = "repaired"


TargetSelector = Literal["selected", "last", "all", "none"]


class ModelMixin:
    def model_copy(self, *, update: dict[str, Any] | None = None) -> Any:
        copied = deepcopy(self)
        for key, value in (update or {}).items():
            setattr(copied, key, value)
        return copied

    def model_dump(self) -> dict[str, Any]:
        return _to_jsonable(self)


def _enum_value(enum_type: type[Enum], value: Any) -> Any:
    if value is None or isinstance(value, enum_type):
        return value
    return enum_type(value)


def _clamp(value: float, min_value: float, max_value: float) -> float:
    return max(min_value, min(max_value, value))


def _to_jsonable(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return {item.name: _to_jsonable(getattr(value, item.name)) for item in fields(value)}
    if isinstance(value, list):
        return [_to_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {key: _to_jsonable(item) for key, item in value.items()}
    return value


@dataclass
class DrawingStyle(ModelMixin):
    stroke: str | None = "#1f2937"
    fill: str | None = None
    line_width: float = 4.0
    opacity: float = 1.0
    dashed: bool = False

    def __post_init__(self) -> None:
        self.stroke = self._normalize_color(self.stroke)
        self.fill = self._normalize_color(self.fill)
        self.line_width = _clamp(float(self.line_width), 0.5, 48.0)
        self.opacity = _clamp(float(self.opacity), 0.05, 1.0)
        self.dashed = bool(self.dashed)

    @staticmethod
    def _normalize_color(value: str | None) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str) or not value.startswith("#") or len(value) not in {4, 7}:
            raise ValueError("color must be a hex value such as #ff0000")
        return value.lower()


@dataclass
class Geometry(ModelMixin):
    x: float | None = None
    y: float | None = None
    x2: float | None = None
    y2: float | None = None
    width: float | None = None
    height: float | None = None
    radius: float | None = None

    def __post_init__(self) -> None:
        for key in ("x", "y", "x2", "y2"):
            value = getattr(self, key)
            if value is not None:
                setattr(self, key, _clamp(float(value), 0.0, 1.0))
        for key in ("width", "height"):
            value = getattr(self, key)
            if value is not None:
                setattr(self, key, _clamp(float(value), 0.01, 1.0))
        if self.radius is not None:
            self.radius = _clamp(float(self.radius), 0.01, 0.6)


@dataclass
class PathCommand(ModelMixin):
    command: str
    x: float | None = None
    y: float | None = None
    x1: float | None = None
    y1: float | None = None
    x2: float | None = None
    y2: float | None = None

    def __post_init__(self) -> None:
        self.command = str(self.command).upper()
        if self.command not in {"M", "L", "Q", "C", "Z"}:
            raise ValueError("path command must be one of M, L, Q, C, Z")
        for key in ("x", "y", "x1", "y1", "x2", "y2"):
            value = getattr(self, key)
            if value is not None:
                setattr(self, key, _clamp(float(value), 0.0, 1.0))


@dataclass
class Vector(ModelMixin):
    dx: float = 0
    dy: float = 0

    def __post_init__(self) -> None:
        self.dx = _clamp(float(self.dx), -1.0, 1.0)
        self.dy = _clamp(float(self.dy), -1.0, 1.0)


@dataclass
class DrawingOperation(ModelMixin):
    type: OperationType
    shape: ShapeType | None = None
    target: TargetSelector | None = None
    style: DrawingStyle | dict[str, Any] | None = None
    geometry: Geometry | dict[str, Any] | None = None
    text: str | None = None
    value: str | None = None
    amount: float | None = None
    delta: Vector | dict[str, Any] | None = None
    path: list[PathCommand | dict[str, Any]] | None = None
    group_id: str | None = None
    description: str = ""

    def __post_init__(self) -> None:
        self.type = _enum_value(OperationType, self.type)
        self.shape = _enum_value(ShapeType, self.shape)
        if isinstance(self.style, dict):
            self.style = DrawingStyle(**self.style)
        if isinstance(self.geometry, dict):
            self.geometry = Geometry(**self.geometry)
        if isinstance(self.delta, dict):
            self.delta = Vector(**self.delta)
        if self.path is not None:
            self.path = [item if isinstance(item, PathCommand) else PathCommand(**item) for item in self.path]


@dataclass
class CommandRequest(ModelMixin):
    transcript: str
    locale: str = "zh-CN"
    canvas_width: int = 1280
    canvas_height: int = 720
    selected_ids: list[str] = field(default_factory=list)
    recent_object_ids: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.transcript = str(self.transcript).strip()
        if not self.transcript:
            raise ValueError("transcript is required")
        self.transcript = self.transcript[:2000]
        self.locale = str(self.locale or "zh-CN")
        self.canvas_width = max(100, min(10000, int(self.canvas_width)))
        self.canvas_height = max(100, min(10000, int(self.canvas_height)))
        self.selected_ids = [str(item) for item in self.selected_ids]
        self.recent_object_ids = [str(item) for item in self.recent_object_ids]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CommandRequest:
        return cls(
            transcript=data.get("transcript", ""),
            locale=data.get("locale", "zh-CN"),
            canvas_width=data.get("canvas_width", 1280),
            canvas_height=data.get("canvas_height", 720),
            selected_ids=data.get("selected_ids") or [],
            recent_object_ids=data.get("recent_object_ids") or [],
        )


@dataclass
class CommandPlan(ModelMixin):
    operations: list[DrawingOperation | dict[str, Any]] = field(default_factory=list)
    confidence: float = 0.0
    needs_confirmation: bool = False
    spoken_feedback: str = ""
    warnings: list[str] = field(default_factory=list)
    source: PlanSource = PlanSource.RULE
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.operations = [
            operation if isinstance(operation, DrawingOperation) else DrawingOperation(**operation)
            for operation in self.operations
        ]
        self.confidence = _clamp(float(self.confidence), 0.0, 1.0)
        self.needs_confirmation = bool(self.needs_confirmation)
        self.warnings = [str(item) for item in self.warnings]
        self.source = _enum_value(PlanSource, self.source)
        self.metadata = dict(self.metadata or {})
