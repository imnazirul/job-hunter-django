"""OpenRouter chat client built for a weak model with a small context window.

The contract every caller can rely on: complete_json either returns an object
that passed the caller's own validator, or raises. It never returns half-parsed
junk, and it never retries more than once, so a misbehaving model costs at most
two calls before the caller falls back to something deterministic.
"""

import json
import logging

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


class LLMError(Exception):
    pass


class LLMUnavailable(LLMError):
    """No API key, network failure, rate limit, or provider-side error."""


class LLMBadOutput(LLMError):
    """The model answered, but not with JSON we can use."""


def is_configured():
    return bool(settings.OPENROUTER_API_KEY)


def complete_json(system, user, validate, *, max_tokens=900, temperature=0.1):
    """Return validate(parsed_json) from the model, retrying bad JSON once.

    validate is given the parsed object and must return a cleaned version or
    raise LLMBadOutput. Putting validation in the caller keeps this module
    ignorant of profiles and job scores.
    """
    if not is_configured():
        raise LLMUnavailable("OPENROUTER_API_KEY is not set")

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]

    raw = _chat(messages, max_tokens=max_tokens, temperature=temperature)
    try:
        return validate(_parse_json(raw))
    except LLMBadOutput as first_failure:
        logger.warning("LLM returned unusable JSON, retrying once: %s", first_failure)

    messages.append({"role": "assistant", "content": raw})
    messages.append(
        {
            "role": "user",
            "content": (
                "That was not valid JSON matching the requested shape. "
                "Reply with the JSON only. No prose, no markdown fences, no explanation."
            ),
        }
    )
    retry_raw = _chat(messages, max_tokens=max_tokens, temperature=0.0)
    return validate(_parse_json(retry_raw))


def _chat(messages, *, max_tokens, temperature):
    url = f"{settings.OPENROUTER_BASE_URL.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": settings.OPENROUTER_APP_URL,
        "X-Title": settings.OPENROUTER_APP_NAME,
    }
    payload = {
        "model": settings.OPENROUTER_MODEL,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }

    try:
        response = requests.post(
            url, headers=headers, json=payload, timeout=settings.OPENROUTER_TIMEOUT
        )
    except requests.RequestException as exc:
        raise LLMUnavailable(f"request to OpenRouter failed: {exc}") from exc

    if response.status_code == 429:
        raise LLMUnavailable(f"rate limited by OpenRouter: {response.text[:300]}")
    if response.status_code >= 400:
        raise LLMUnavailable(
            f"OpenRouter returned {response.status_code}: {response.text[:300]}"
        )

    try:
        body = response.json()
    except ValueError as exc:
        raise LLMUnavailable(f"OpenRouter response was not JSON: {response.text[:300]}") from exc

    # OpenRouter tunnels upstream provider errors inside a 200 body.
    if "error" in body and not body.get("choices"):
        raise LLMUnavailable(f"OpenRouter error: {str(body['error'])[:300]}")

    try:
        content = body["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise LLMUnavailable(f"unexpected OpenRouter response shape: {str(body)[:300]}") from exc

    if not isinstance(content, str) or not content.strip():
        raise LLMBadOutput("model returned an empty message")

    usage = body.get("usage") or {}
    logger.info(
        "llm call model=%s prompt_tokens=%s completion_tokens=%s",
        body.get("model", settings.OPENROUTER_MODEL),
        usage.get("prompt_tokens"),
        usage.get("completion_tokens"),
    )
    return content


def _parse_json(text):
    """Pull the first JSON object or array out of a model reply.

    Weak models wrap JSON in fences, prefix it with "Here is the JSON:", or
    append a closing remark. Locating the outermost balanced brackets handles
    all three without a regex we would have to debug at 2am.
    """
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = _strip_code_fence(cleaned)

    candidate = _first_balanced_span(cleaned)
    if candidate is None:
        raise LLMBadOutput(f"no JSON object or array found in reply: {cleaned[:200]!r}")

    try:
        return json.loads(candidate)
    except ValueError as exc:
        raise LLMBadOutput(f"JSON did not parse: {exc}; text was {candidate[:200]!r}") from exc


def _strip_code_fence(text):
    lines = text.splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    while lines and lines[-1].strip() in {"```", ""}:
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _first_balanced_span(text):
    openers = {"{": "}", "[": "]"}
    start = next((i for i, ch in enumerate(text) if ch in openers), None)
    if start is None:
        return None

    opener = text[start]
    closer = openers[opener]
    depth = 0
    in_string = False
    escaped = False

    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == opener:
            depth += 1
        elif char == closer:
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    return None
