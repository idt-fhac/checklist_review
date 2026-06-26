import re
import unicodedata
from pathlib import Path


def slug(name: str) -> str:
    return name.strip().replace(" ", "_").lower() or "process"


def get_project_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent.parent.parent.parent


def clean_text_for_encoding(text: str) -> str:
    if not text:
        return text

    if not isinstance(text, str):
        text = str(text)

    text = text.replace("\u200b", "")

    zero_width_chars = [
        "\u200c",
        "\u200d",
        "\ufeff",
        "\u200e",
        "\u200f",
        "\u202a",
        "\u202b",
        "\u202c",
        "\u202d",
        "\u202e",
        "\u2060",
        "\u2061",
        "\u2062",
        "\u2063",
        "\u2064",
    ]
    for char in zero_width_chars:
        text = text.replace(char, "")

    result = []
    for char in text:
        cat = unicodedata.category(char)
        if cat == "Cf":
            continue
        if cat.startswith("C") and char not in "\n\r\t ":
            continue
        result.append(char)

    result = "".join(result)

    zero_width_pattern = re.compile(
        r"[\u200b\u200c\u200d\ufeff\u200e\u200f\u202a\u202b\u202c\u202d\u202e\u2060\u2061\u2062\u2063\u2064]"
    )
    result = zero_width_pattern.sub("", result)

    try:
        result = unicodedata.normalize("NFKC", result)
    except Exception:
        pass

    result = re.sub(r"[ \t]+", " ", result)
    result = re.sub(r"[ \t]*\n[ \t]*", "\n", result)

    return result


try:
    import httpx

    _original_normalize_header_value = httpx._models._normalize_header_value

    def _patched_normalize_header_value(value, encoding=None):
        if isinstance(value, str):
            value = clean_text_for_encoding(value)
        return _original_normalize_header_value(value, encoding)

    httpx._models._normalize_header_value = _patched_normalize_header_value
except (ImportError, AttributeError):
    pass
