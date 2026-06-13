from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class OperationType(str, Enum):
    DRAW_SHAPE = "draw_shape"
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
    LINE = "line"
    ARROW = "arrow"
    RECTANGLE = "rectangle"
    CIRCLE = "circle"
    ELLIPSE = "ellipse"
    TRIANGLE = "triangle"
    TEXT = "text"


class PlanSource(str, Enum):
    RULE = "rule"
    LLM = "llm"
    REPAIRED = "repaired"


TargetSelector = Literal["selected", "last", "all", "none"]


class DrawingStyle(BaseModel):
    stroke: str | None = Field(default="#1f2937", description="Hex stroke color.")
    fill: str | None = Field(default=None, description="Hex fill color or null for transparent.")
    line_width: float = Field(default=4.0, ge=0.5, le=48)
    opacity: float = Field(default=1.0, ge=0.05, le=1.0)
    dashed: bool = False

    @field_validator("stroke", "fill")
    @classmethod
    def validate_color(cls, value: str | None) -> str | None:
        if value is None:
            return value
        if not value.startswith("#") or len(value) not in {4, 7}:
            raise ValueError("color must be a hex value such as #ff0000")
        return value.lower()


class Geometry(BaseModel):
    x: float | None = Field(default=None, ge=0, le=1)
    y: float | None = Field(default=None, ge=0, le=1)
    x2: float | None = Field(default=None, ge=0, le=1)
    y2: float | None = Field(default=None, ge=0, le=1)
    width: float | None = Field(default=None, ge=0.01, le=1)
    height: float | None = Field(default=None, ge=0.01, le=1)
    radius: float | None = Field(default=None, ge=0.01, le=0.6)


class Vector(BaseModel):
    dx: float = Field(default=0, ge=-1, le=1)
    dy: float = Field(default=0, ge=-1, le=1)


class DrawingOperation(BaseModel):
    type: OperationType
    shape: ShapeType | None = None
    target: TargetSelector | None = None
    style: DrawingStyle | None = None
    geometry: Geometry | None = None
    text: str | None = None
    value: str | None = None
    amount: float | None = None
    delta: Vector | None = None
    description: str = ""


class CommandRequest(BaseModel):
    transcript: str = Field(..., min_length=1, max_length=2000)
    locale: str = "zh-CN"
    canvas_width: int = Field(default=1280, ge=100, le=10000)
    canvas_height: int = Field(default=720, ge=100, le=10000)
    selected_ids: list[str] = Field(default_factory=list)
    recent_object_ids: list[str] = Field(default_factory=list)


class CommandPlan(BaseModel):
    operations: list[DrawingOperation] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0, le=1)
    needs_confirmation: bool = False
    spoken_feedback: str = ""
    warnings: list[str] = Field(default_factory=list)
    source: PlanSource = PlanSource.RULE
