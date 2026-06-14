from __future__ import annotations

import re

from backend.domain.models import DrawingStyle


# 中文颜色关键词到前端十六进制颜色的映射，长词优先匹配。
COLOR_ALIASES: dict[str, str] = {
    "黑色": "#111827",
    "黑": "#111827",
    "白色": "#ffffff",
    "白": "#ffffff",
    "红色": "#ef4444",
    "红": "#ef4444",
    "橙色": "#f97316",
    "橙": "#f97316",
    "黄色": "#facc15",
    "黄": "#facc15",
    "绿色": "#22c55e",
    "绿": "#22c55e",
    "青色": "#06b6d4",
    "青": "#06b6d4",
    "蓝色": "#3b82f6",
    "蓝": "#3b82f6",
    "紫色": "#8b5cf6",
    "紫": "#8b5cf6",
    "粉色": "#ec4899",
    "粉": "#ec4899",
    "灰色": "#6b7280",
    "灰": "#6b7280",
    "棕色": "#92400e",
    "棕": "#92400e",
    "金色": "#f59e0b",
    "金": "#f59e0b",
}

# 允许用户直接说出或输入 #rgb / #rrggbb 颜色值。
HEX_RE = re.compile(r"#[0-9a-fA-F]{3}(?:[0-9a-fA-F]{3})?")


def extract_color(text: str) -> str | None:
    """从自然语言文本中提取颜色，优先识别显式十六进制值。"""
    hex_match = HEX_RE.search(text)
    if hex_match:
        return hex_match.group(0).lower()

    # 先匹配“红色”等长词，再匹配“红”等短词，避免短词抢占。
    for name in sorted(COLOR_ALIASES, key=len, reverse=True):
        if name in text:
            return COLOR_ALIASES[name]
    return None


def wants_transparent_fill(text: str) -> bool:
    """判断用户是否明确要求不要填充。"""
    return any(keyword in text for keyword in ("透明", "无填充", "不要填充", "空心"))


def wants_fill(text: str) -> bool:
    """判断用户是否倾向使用填充色而不是只有描边。"""
    return any(keyword in text for keyword in ("填充", "实心", "涂满", "色块", "背景色"))


def extract_line_width(text: str) -> float:
    """根据中文粗细描述推断线宽，并限制在 DrawingStyle 支持范围内。"""
    width_match = re.search(r"(?:线宽|粗细|宽度)\s*(\d+(?:\.\d+)?)", text)
    if width_match:
        return max(0.5, min(48.0, float(width_match.group(1))))
    if any(keyword in text for keyword in ("很粗", "粗线", "加粗")):
        return 9.0
    if "粗" in text:
        return 6.0
    if any(keyword in text for keyword in ("细线", "细一点", "细")):
        return 2.0
    return 4.0


def extract_opacity(text: str) -> float:
    """根据透明度关键词推断整体不透明度。"""
    if "半透明" in text:
        return 0.55
    if "透明" in text and not wants_transparent_fill(text):
        return 0.35
    return 1.0


def build_style(text: str, *, default_color: str = "#1f2937", prefer_fill: bool = False) -> DrawingStyle:
    """把文本中的颜色、填充、线宽和透明度描述合成 DrawingStyle。"""
    color = extract_color(text) or default_color
    fill = None
    stroke = color

    # prefer_fill 用于预设图形和文本，让它们默认呈现实心效果。
    if wants_fill(text) or prefer_fill:
        fill = color
    if wants_transparent_fill(text):
        fill = None

    return DrawingStyle(
        stroke=stroke,
        fill=fill,
        line_width=extract_line_width(text),
        opacity=extract_opacity(text),
        dashed="虚线" in text,
    )
