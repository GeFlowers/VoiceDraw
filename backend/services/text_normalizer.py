from __future__ import annotations

import re
import unicodedata


# 中文数字到阿拉伯数字的最小映射，覆盖常见语音尺寸/角度表达。
CN_DIGITS = {
    "零": 0,
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
}


def normalize_text(text: str) -> str:
    """统一文本宽度、大小写和分隔符，降低后续规则匹配复杂度。"""
    normalized = unicodedata.normalize("NFKC", text).strip().lower()
    # 把不同中文/英文停顿符统一成句号，方便拆成多个子命令。
    normalized = normalized.replace("，", "。").replace(",", "。")
    normalized = normalized.replace("；", "。").replace(";", "。")
    normalized = normalized.replace("、", "。")
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized


def split_compound_commands(text: str) -> list[str]:
    """把“先画圆再画线”这类复合语音拆成独立片段。"""
    marked = re.sub(r"(然后|接着|之后|随后|并且|同时|另外|再给|再画|再写|再加)", "。", text)
    # “和/还有”只有在后面像一个新命令时才拆分，避免误切普通短语。
    marked = re.sub(r"(以及|还有|和)(?=(一个|一条|一段|一座|一棵|一朵|画|添加|写|放|在))", "。", marked)
    parts = [part.strip(" 。") for part in marked.split("。")]
    return [part for part in parts if part]


def chinese_number_to_int(value: str) -> int | None:
    """解析 0 到 99 范围内的常见中文数字。"""
    value = value.strip()
    if not value:
        return None
    if value.isdigit():
        return int(value)
    if value in CN_DIGITS:
        return CN_DIGITS[value]
    if "十" in value:
        left, _, right = value.partition("十")
        tens = CN_DIGITS.get(left, 1) if left else 1
        ones = CN_DIGITS.get(right, 0) if right else 0
        return tens * 10 + ones
    return None


def extract_first_number(text: str) -> float | None:
    """优先提取阿拉伯数字，未命中时尝试提取中文数字。"""
    match = re.search(r"(\d+(?:\.\d+)?)", text)
    if match:
        return float(match.group(1))

    cn_match = re.search(r"([零一二两三四五六七八九十]{1,3})", text)
    if cn_match:
        parsed = chinese_number_to_int(cn_match.group(1))
        if parsed is not None:
            return float(parsed)
    return None


def clamp(value: float, min_value: float = 0.0, max_value: float = 1.0) -> float:
    """限制归一化数值范围。"""
    return max(min_value, min(max_value, value))
