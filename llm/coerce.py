"""Coercion helpers for model output.

A weak model will hand back "5 years" where an int was asked for, a comma
string where a list was asked for, and null where a string was asked for.
These turn that into something usable or raise LLMBadOutput, rather than
letting a TypeError surface three layers away.
"""

from .client import LLMBadOutput


def require_mapping(value, what="response"):
    if not isinstance(value, dict):
        raise LLMBadOutput(f"expected a JSON object for {what}, got {type(value).__name__}")
    return value


def require_list(value, what="response"):
    if not isinstance(value, list):
        raise LLMBadOutput(f"expected a JSON array for {what}, got {type(value).__name__}")
    return value


def as_text(value, *, max_length=None, default=""):
    if value is None:
        return default
    if isinstance(value, (int, float)):
        value = str(value)
    if not isinstance(value, str):
        return default
    text = " ".join(value.split())
    if max_length is not None:
        text = text[:max_length]
    return text


def as_text_list(value, *, max_items, max_length=80):
    """Accept a list, or a comma/newline separated string, and dedupe it."""
    if value is None:
        return []
    if isinstance(value, str):
        parts = [part for chunk in value.splitlines() for part in chunk.split(",")]
    elif isinstance(value, list):
        parts = [part if isinstance(part, str) else str(part) for part in value]
    else:
        return []

    seen = set()
    result = []
    for part in parts:
        text = as_text(part, max_length=max_length)
        if not text:
            continue
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(text)
        if len(result) >= max_items:
            break
    return result


def as_int(value, *, minimum=None, maximum=None, default=None):
    if isinstance(value, bool):
        return default
    if isinstance(value, (int, float)):
        number = int(value)
    elif isinstance(value, str):
        digits = "".join(char for char in value if char.isdigit())
        if not digits:
            return default
        number = int(digits)
    else:
        return default

    if minimum is not None:
        number = max(number, minimum)
    if maximum is not None:
        number = min(number, maximum)
    return number


def as_choice(value, choices, default):
    text = as_text(value).casefold()
    for choice in choices:
        if text == choice.casefold():
            return choice
    return default
