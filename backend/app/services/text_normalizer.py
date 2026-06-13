from __future__ import annotations

import re
import unicodedata


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
    normalized = unicodedata.normalize("NFKC", text).strip().lower()
    normalized = normalized.replace("，", "。").replace(",", "。")
    normalized = normalized.replace("；", "。").replace(";", "。")
    normalized = normalized.replace("、", "。")
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized


def split_compound_commands(text: str) -> list[str]:
    marked = re.sub(r"(然后|接着|之后|随后|并且|同时|另外|再给|再画|再写|再加)", "。", text)
    marked = re.sub(r"(以及|还有|和)(?=(一个|一条|一段|一座|一棵|一朵|画|添加|写|放|在))", "。", marked)
    parts = [part.strip(" 。") for part in marked.split("。")]
    return [part for part in parts if part]


def chinese_number_to_int(value: str) -> int | None:
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
    return max(min_value, min(max_value, value))
