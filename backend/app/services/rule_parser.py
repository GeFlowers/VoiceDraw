from __future__ import annotations

import re
from dataclasses import dataclass, field

from backend.app.domain.models import (
    CommandPlan,
    CommandRequest,
    DrawingOperation,
    Geometry,
    OperationType,
    PlanSource,
    ShapeType,
    Vector,
)
from backend.app.services.colors import build_style, extract_color
from backend.app.services.text_normalizer import (
    clamp,
    extract_first_number,
    normalize_text,
    split_compound_commands,
)


ANCHORS: dict[str, tuple[float, float]] = {
    "左上角": (0.2, 0.22),
    "右上角": (0.8, 0.22),
    "左下角": (0.2, 0.78),
    "右下角": (0.8, 0.78),
    "左上": (0.2, 0.22),
    "右上": (0.8, 0.22),
    "左下": (0.2, 0.78),
    "右下": (0.8, 0.78),
    "左边": (0.22, 0.5),
    "右边": (0.78, 0.5),
    "上方": (0.5, 0.22),
    "下方": (0.5, 0.78),
    "顶部": (0.5, 0.18),
    "底部": (0.5, 0.82),
    "中央": (0.5, 0.5),
    "中间": (0.5, 0.5),
    "中心": (0.5, 0.5),
}

SHAPE_KEYWORDS: list[tuple[ShapeType, tuple[str, ...]]] = [
    (ShapeType.ARROW, ("箭头", "箭线")),
    (ShapeType.LINE, ("直线", "线段", "一条线", "线")),
    (ShapeType.RECTANGLE, ("长方形", "矩形", "方框", "方块", "正方形")),
    (ShapeType.CIRCLE, ("圆形", "圆圈", "圆")),
    (ShapeType.ELLIPSE, ("椭圆",)),
    (ShapeType.TRIANGLE, ("三角形", "三角")),
]


@dataclass
class SegmentResult:
    operations: list[DrawingOperation] = field(default_factory=list)
    confidence: float = 0.0
    warnings: list[str] = field(default_factory=list)


class RuleBasedParser:
    """Fast local parser for common drawing commands.

    The parser intentionally favors deterministic behavior for latency-sensitive
    voice commands. The LangGraph layer decides when to ask an LLM for repair or
    decomposition.
    """

    def parse(self, request: CommandRequest) -> CommandPlan:
        normalized = normalize_text(request.transcript)
        segments = split_compound_commands(normalized)
        results = [self._parse_segment(segment, request) for segment in segments]

        operations: list[DrawingOperation] = []
        warnings: list[str] = []
        confidences: list[float] = []
        for result in results:
            operations.extend(result.operations)
            warnings.extend(result.warnings)
            if result.operations:
                confidences.append(result.confidence)

        if not operations:
            return CommandPlan(
                operations=[
                    DrawingOperation(
                        type=OperationType.NO_OP,
                        description="No deterministic command matched.",
                    )
                ],
                confidence=0.2,
                spoken_feedback="我没有准确理解这条绘图指令，请换一种说法。",
                warnings=["规则解析未匹配到可执行绘图动作。"],
                source=PlanSource.RULE,
            )

        confidence = min(0.98, sum(confidences) / max(1, len(confidences)))
        return CommandPlan(
            operations=operations,
            confidence=confidence,
            spoken_feedback=self._feedback_for_operations(operations),
            warnings=warnings,
            source=PlanSource.RULE,
        )

    def _parse_segment(self, segment: str, request: CommandRequest) -> SegmentResult:
        if self._contains_any(segment, ("撤销", "后退一步", "退回一步")):
            return self._single(OperationType.UNDO, "撤销上一步", 0.98)

        if self._contains_any(segment, ("重做", "恢复上一步", "取消撤销")):
            return self._single(OperationType.REDO, "恢复被撤销的步骤", 0.98)

        if self._contains_any(segment, ("清空", "清除画布", "清屏", "新建画布", "重新开始")):
            return self._single(OperationType.CLEAR, "清空画布", 0.98)

        if self._contains_any(segment, ("导出", "下载", "保存图片", "保存画布")):
            return self._single(OperationType.EXPORT, "导出当前画布", 0.96, value="png")

        if "背景" in segment:
            return self._parse_background(segment)

        if self._looks_like_style_update(segment):
            return self._parse_style_update(segment, request)

        if self._contains_any(segment, ("选择", "选中")):
            return self._parse_select(segment, request)

        if self._contains_any(segment, ("删除", "删掉", "移除", "去掉")):
            return self._parse_delete(segment, request)

        if self._looks_like_move(segment):
            return self._parse_move(segment, request)

        if self._contains_any(segment, ("放大", "缩小", "变大", "变小")):
            return self._parse_resize(segment, request)

        if self._contains_any(segment, ("旋转", "转动", "顺时针", "逆时针")):
            return self._parse_rotate(segment, request)

        text_result = self._parse_text(segment)
        if text_result.operations:
            return text_result

        preset_result = self._parse_presets(segment)
        if preset_result.operations:
            return preset_result

        shape_result = self._parse_shape(segment)
        if shape_result.operations:
            return shape_result

        return SegmentResult(warnings=[f"未识别片段: {segment}"])

    def _parse_background(self, segment: str) -> SegmentResult:
        color = extract_color(segment)
        if "透明" in segment:
            color = "transparent"
        if color is None:
            return SegmentResult(
                confidence=0.42,
                warnings=["检测到背景指令，但没有识别到颜色。"],
            )
        return self._single(
            OperationType.SET_BACKGROUND,
            f"设置背景为 {color}",
            0.94,
            value=color,
        )

    def _parse_style_update(self, segment: str, request: CommandRequest) -> SegmentResult:
        style = build_style(segment)
        target = self._detect_target(segment, request)
        return SegmentResult(
            operations=[
                DrawingOperation(
                    type=OperationType.SET_STYLE,
                    target=target,
                    style=style,
                    description="更新选中对象样式",
                )
            ],
            confidence=0.78,
        )

    def _parse_select(self, segment: str, request: CommandRequest) -> SegmentResult:
        target = self._detect_target(segment, request, default="last")
        return SegmentResult(
            operations=[
                DrawingOperation(
                    type=OperationType.SELECT,
                    target=target,
                    description=f"选择 {target}",
                )
            ],
            confidence=0.88,
        )

    def _parse_delete(self, segment: str, request: CommandRequest) -> SegmentResult:
        target = self._detect_target(segment, request)
        return SegmentResult(
            operations=[
                DrawingOperation(
                    type=OperationType.DELETE,
                    target=target,
                    description=f"删除 {target}",
                )
            ],
            confidence=0.9,
        )

    def _parse_move(self, segment: str, request: CommandRequest) -> SegmentResult:
        dx, dy = 0.0, 0.0
        distance = self._movement_distance(segment, request)
        if self._contains_any(segment, ("左", "向左", "往左")):
            dx -= distance
        if self._contains_any(segment, ("右", "向右", "往右")):
            dx += distance
        if self._contains_any(segment, ("上", "向上", "往上")):
            dy -= distance
        if self._contains_any(segment, ("下", "向下", "往下")):
            dy += distance
        if dx == 0 and dy == 0:
            return SegmentResult(warnings=["检测到移动指令，但没有方向。"])

        return SegmentResult(
            operations=[
                DrawingOperation(
                    type=OperationType.MOVE,
                    target=self._detect_target(segment, request),
                    delta=Vector(dx=clamp(dx, -1, 1), dy=clamp(dy, -1, 1)),
                    description="移动对象",
                )
            ],
            confidence=0.86,
        )

    def _parse_resize(self, segment: str, request: CommandRequest) -> SegmentResult:
        number = extract_first_number(segment)
        if number and number > 2:
            amount = 1 + number / 100 if self._contains_any(segment, ("放大", "变大")) else 1 - number / 100
        else:
            amount = 1.18 if self._contains_any(segment, ("放大", "变大")) else 0.84
        amount = max(0.1, min(4.0, amount))
        return SegmentResult(
            operations=[
                DrawingOperation(
                    type=OperationType.RESIZE,
                    target=self._detect_target(segment, request),
                    amount=amount,
                    description="缩放对象",
                )
            ],
            confidence=0.84,
        )

    def _parse_rotate(self, segment: str, request: CommandRequest) -> SegmentResult:
        amount = extract_first_number(segment) or 15.0
        if "逆时针" in segment:
            amount = -amount
        return SegmentResult(
            operations=[
                DrawingOperation(
                    type=OperationType.ROTATE,
                    target=self._detect_target(segment, request),
                    amount=amount,
                    description="旋转对象",
                )
            ],
            confidence=0.84,
        )

    def _parse_text(self, segment: str) -> SegmentResult:
        if not self._contains_any(segment, ("写", "文字", "标题", "标注", "标签")):
            return SegmentResult()

        text = self._extract_text(segment)
        if not text:
            return SegmentResult(
                confidence=0.38,
                warnings=["检测到文字指令，但没有提取到文字内容。"],
            )

        x, y = self._anchor_for(segment, default=(0.5, 0.5))
        style = build_style(segment, default_color="#111827", prefer_fill=True)
        return SegmentResult(
            operations=[
                DrawingOperation(
                    type=OperationType.ADD_TEXT,
                    shape=ShapeType.TEXT,
                    text=text,
                    style=style,
                    geometry=Geometry(x=x, y=y, height=0.08),
                    description=f"添加文字 {text}",
                )
            ],
            confidence=0.82,
        )

    def _parse_presets(self, segment: str) -> SegmentResult:
        operations: list[DrawingOperation] = []
        if "太阳" in segment:
            operations.extend(self._preset_sun(segment))
        if "房子" in segment or "房屋" in segment:
            operations.extend(self._preset_house(segment))
        if "树" in segment:
            operations.extend(self._preset_tree(segment))
        if "云" in segment or "云朵" in segment:
            operations.extend(self._preset_cloud(segment))
        if "山" in segment:
            operations.extend(self._preset_mountains(segment))

        if not operations:
            return SegmentResult()
        return SegmentResult(operations=operations, confidence=0.76)

    def _parse_shape(self, segment: str) -> SegmentResult:
        shape = self._detect_shape(segment)
        if shape is None:
            return SegmentResult()

        style = build_style(segment, prefer_fill=self._shape_prefers_fill(segment, shape))
        geometry = self._geometry_for_shape(segment, shape)
        return SegmentResult(
            operations=[
                DrawingOperation(
                    type=OperationType.DRAW_SHAPE,
                    shape=shape,
                    style=style,
                    geometry=geometry,
                    description=f"绘制 {shape.value}",
                )
            ],
            confidence=0.84,
        )

    def _preset_sun(self, segment: str) -> list[DrawingOperation]:
        x, y = self._anchor_for(segment, default=(0.78, 0.22))
        color = extract_color(segment) or "#facc15"
        style = build_style(segment, default_color=color, prefer_fill=True)
        ops = [
            DrawingOperation(
                type=OperationType.DRAW_SHAPE,
                shape=ShapeType.CIRCLE,
                style=style,
                geometry=Geometry(x=x, y=y, radius=0.07),
                description="绘制太阳主体",
            )
        ]
        for dx, dy in ((0, -0.13), (0.09, -0.09), (0.13, 0), (0.09, 0.09), (0, 0.13), (-0.09, 0.09), (-0.13, 0), (-0.09, -0.09)):
            ops.append(
                DrawingOperation(
                    type=OperationType.DRAW_SHAPE,
                    shape=ShapeType.LINE,
                    style=style,
                    geometry=Geometry(
                        x=clamp(x + dx * 0.55),
                        y=clamp(y + dy * 0.55),
                        x2=clamp(x + dx),
                        y2=clamp(y + dy),
                    ),
                    description="绘制太阳光线",
                )
            )
        return ops

    def _preset_house(self, segment: str) -> list[DrawingOperation]:
        x, y = self._anchor_for(segment, default=(0.38, 0.58))
        wall_style = build_style(segment, default_color=extract_color(segment) or "#f97316", prefer_fill=True)
        roof_style = build_style("红色 填充", default_color="#ef4444", prefer_fill=True)
        door_style = build_style("棕色 填充", default_color="#92400e", prefer_fill=True)
        return [
            DrawingOperation(
                type=OperationType.DRAW_SHAPE,
                shape=ShapeType.RECTANGLE,
                style=wall_style,
                geometry=Geometry(x=x, y=y + 0.06, width=0.22, height=0.18),
                description="绘制房子墙体",
            ),
            DrawingOperation(
                type=OperationType.DRAW_SHAPE,
                shape=ShapeType.TRIANGLE,
                style=roof_style,
                geometry=Geometry(x=x, y=y - 0.09, width=0.26, height=0.17),
                description="绘制房顶",
            ),
            DrawingOperation(
                type=OperationType.DRAW_SHAPE,
                shape=ShapeType.RECTANGLE,
                style=door_style,
                geometry=Geometry(x=x, y=y + 0.11, width=0.06, height=0.09),
                description="绘制门",
            ),
        ]

    def _preset_tree(self, segment: str) -> list[DrawingOperation]:
        x, y = self._anchor_for(segment, default=(0.68, 0.62))
        trunk_style = build_style("棕色 填充", default_color="#92400e", prefer_fill=True)
        leaf_style = build_style(segment, default_color="#22c55e", prefer_fill=True)
        return [
            DrawingOperation(
                type=OperationType.DRAW_SHAPE,
                shape=ShapeType.RECTANGLE,
                style=trunk_style,
                geometry=Geometry(x=x, y=y + 0.07, width=0.055, height=0.15),
                description="绘制树干",
            ),
            DrawingOperation(
                type=OperationType.DRAW_SHAPE,
                shape=ShapeType.CIRCLE,
                style=leaf_style,
                geometry=Geometry(x=x, y=y - 0.05, radius=0.11),
                description="绘制树冠",
            ),
        ]

    def _preset_cloud(self, segment: str) -> list[DrawingOperation]:
        x, y = self._anchor_for(segment, default=(0.28, 0.24))
        style = build_style(segment, default_color="#94a3b8", prefer_fill=True)
        return [
            DrawingOperation(
                type=OperationType.DRAW_SHAPE,
                shape=ShapeType.ELLIPSE,
                style=style,
                geometry=Geometry(x=x - 0.06, y=y, width=0.14, height=0.08),
                description="绘制云朵",
            ),
            DrawingOperation(
                type=OperationType.DRAW_SHAPE,
                shape=ShapeType.ELLIPSE,
                style=style,
                geometry=Geometry(x=x + 0.04, y=y - 0.025, width=0.17, height=0.1),
                description="绘制云朵",
            ),
            DrawingOperation(
                type=OperationType.DRAW_SHAPE,
                shape=ShapeType.ELLIPSE,
                style=style,
                geometry=Geometry(x=x + 0.12, y=y + 0.01, width=0.12, height=0.07),
                description="绘制云朵",
            ),
        ]

    def _preset_mountains(self, segment: str) -> list[DrawingOperation]:
        x, y = self._anchor_for(segment, default=(0.5, 0.72))
        style = build_style(segment, default_color="#64748b", prefer_fill=True)
        return [
            DrawingOperation(
                type=OperationType.DRAW_SHAPE,
                shape=ShapeType.TRIANGLE,
                style=style,
                geometry=Geometry(x=x - 0.12, y=y, width=0.3, height=0.28),
                description="绘制山峰",
            ),
            DrawingOperation(
                type=OperationType.DRAW_SHAPE,
                shape=ShapeType.TRIANGLE,
                style=style,
                geometry=Geometry(x=x + 0.12, y=y + 0.03, width=0.26, height=0.23),
                description="绘制山峰",
            ),
        ]

    def _geometry_for_shape(self, segment: str, shape: ShapeType) -> Geometry:
        if shape in {ShapeType.LINE, ShapeType.ARROW}:
            return self._line_geometry(segment)

        x, y = self._anchor_for(segment, default=(0.5, 0.5))
        scale = self._size_scale(segment)
        if shape == ShapeType.CIRCLE:
            return Geometry(x=x, y=y, radius=0.1 * scale)
        if shape == ShapeType.ELLIPSE:
            return Geometry(x=x, y=y, width=0.26 * scale, height=0.16 * scale)
        if shape == ShapeType.TRIANGLE:
            return Geometry(x=x, y=y, width=0.24 * scale, height=0.22 * scale)
        return Geometry(x=x, y=y, width=0.26 * scale, height=0.18 * scale)

    def _line_geometry(self, segment: str) -> Geometry:
        anchor_names = sorted(ANCHORS, key=len, reverse=True)
        spans: list[tuple[int, int]] = []
        matches: list[tuple[int, str, tuple[float, float]]] = []
        for name in anchor_names:
            for match in re.finditer(re.escape(name), segment):
                span = match.span()
                if any(span[0] < existing[1] and span[1] > existing[0] for existing in spans):
                    continue
                spans.append(span)
                matches.append((span[0], name, ANCHORS[name]))
        matches.sort(key=lambda item: item[0])
        if len(matches) >= 2:
            _, _, start = matches[0]
            _, _, end = matches[1]
            return Geometry(x=start[0], y=start[1], x2=end[0], y2=end[1])
        if self._contains_any(segment, ("竖线", "垂直")):
            return Geometry(x=0.5, y=0.22, x2=0.5, y2=0.78)
        if self._contains_any(segment, ("斜线", "对角")):
            return Geometry(x=0.22, y=0.24, x2=0.78, y2=0.76)
        return Geometry(x=0.22, y=0.5, x2=0.78, y2=0.5)

    def _detect_shape(self, segment: str) -> ShapeType | None:
        for shape, keywords in SHAPE_KEYWORDS:
            if self._contains_any(segment, keywords):
                return shape
        return None

    def _anchor_for(self, segment: str, default: tuple[float, float]) -> tuple[float, float]:
        for name in sorted(ANCHORS, key=len, reverse=True):
            if name in segment:
                return ANCHORS[name]
        return default

    def _size_scale(self, segment: str) -> float:
        number = extract_first_number(segment)
        if number and "倍" in segment:
            return max(0.4, min(3.0, number))
        if any(keyword in segment for keyword in ("很大", "大号", "大一点", "大")):
            return 1.35
        if any(keyword in segment for keyword in ("很小", "小号", "小一点", "小")):
            return 0.72
        return 1.0

    def _movement_distance(self, segment: str, request: CommandRequest) -> float:
        if "一点" in segment or "一下" in segment:
            return 0.04
        number = extract_first_number(segment)
        if number is None:
            return 0.08
        if number <= 1:
            return number
        basis = max(request.canvas_width, request.canvas_height, 1)
        return clamp(number / basis, 0.005, 0.5)

    def _detect_target(
        self,
        segment: str,
        request: CommandRequest,
        default: str | None = None,
    ) -> str:
        if self._contains_any(segment, ("全部", "所有", "全选")):
            return "all"
        if self._contains_any(segment, ("最后", "刚才", "上一个")):
            return "last"
        if self._contains_any(segment, ("取消选择", "不选")):
            return "none"
        if default is not None:
            return default
        return "selected" if request.selected_ids else "last"

    def _extract_text(self, segment: str) -> str:
        quoted = re.search(r"[\"'“”‘’](.*?)[\"'“”‘’]", segment)
        if quoted and quoted.group(1).strip():
            return quoted.group(1).strip()

        marker_match = re.search(r"(?:写上|写|添加文字|文字|标题|标注|标签)\s*(.+)", segment)
        if not marker_match:
            return ""
        text = marker_match.group(1)
        text = re.sub(r"(在)?(左上角|右上角|左下角|右下角|左边|右边|上方|下方|中间|中央|中心|顶部|底部)", "", text)
        text = re.sub(r"(红色|蓝色|绿色|黄色|黑色|白色|灰色|紫色|粉色|橙色|棕色|金色)", "", text)
        return text.strip(" 。")

    def _shape_prefers_fill(self, segment: str, shape: ShapeType) -> bool:
        if shape in {ShapeType.LINE, ShapeType.ARROW}:
            return False
        return self._contains_any(segment, ("实心", "填充", "色块"))

    def _looks_like_move(self, segment: str) -> bool:
        return (
            self._contains_any(segment, ("移动", "挪", "移到", "移向", "往", "向"))
            and not self._contains_any(segment, ("画", "直线", "线段", "箭头"))
        )

    def _looks_like_style_update(self, segment: str) -> bool:
        has_color = extract_color(segment) is not None or "透明" in segment
        has_action = self._contains_any(segment, ("改成", "改为", "变成", "颜色", "线宽", "粗细", "填充"))
        return has_color and has_action and "背景" not in segment and not self._contains_any(segment, ("画", "添加", "写"))

    def _feedback_for_operations(self, operations: list[DrawingOperation]) -> str:
        if len(operations) == 1:
            op = operations[0]
            if op.type == OperationType.NO_OP:
                return "我没有准确理解这条绘图指令。"
            return f"已{op.description}。"
        return f"已拆解并执行 {len(operations)} 个绘图动作。"

    def _single(
        self,
        operation_type: OperationType,
        description: str,
        confidence: float,
        *,
        value: str | None = None,
    ) -> SegmentResult:
        return SegmentResult(
            operations=[
                DrawingOperation(
                    type=operation_type,
                    description=description,
                    value=value,
                )
            ],
            confidence=confidence,
        )

    @staticmethod
    def _contains_any(text: str, keywords: tuple[str, ...]) -> bool:
        return any(keyword in text for keyword in keywords)
