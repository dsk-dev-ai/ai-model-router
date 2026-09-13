"""Guardrails: PII redaction and prompt-injection blocking.

Both are opt-in per request via ``RouterSpec`` fields:

- ``redact_pii=True``    redact emails, phones, SSNs, cards, IPs from the
                         outbound prompt (and the cached/assistant text).
- ``block_injection=True``  reject requests whose user content looks like an
                         attempt to override the model's instructions.
"""

from __future__ import annotations

import re
from typing import Any

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PHONE_RE = re.compile(r"(?<!\d)\+?[\d(][\d\s().-]{6,}[\d)]\b")
SSN_RE = re.compile(r"\d{3}-\d{2}-\d{4}")
CC_RE = re.compile(r"(?<!\d)(?:\d[ -]*?){13,16}(?!\d)")
IPV4_RE = re.compile(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b")

_REDACTORS: tuple[tuple[re.Pattern[str], str], ...] = (
    (SSN_RE, "[REDACTED SSN]"),
    (CC_RE, "[REDACTED CARD]"),
    (IPV4_RE, "[REDACTED IP]"),
    (EMAIL_RE, "[REDACTED EMAIL]"),
    (PHONE_RE, "[REDACTED PHONE]"),
)

INJECTION_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        r"ignore (all )?(previous|prior|above) instructions",
        r"ignore (your )?(system prompt|developer instructions)",
        r"you are now (in )?(dev(eloper)? )?mode",
        r"jailbreak",
        r"reveal (your )?(system prompt|instructions|initial message)",
        r"output the (system prompt|initial system message)",
        r"pretend (you|to|.*model) ?(are|to be) .* (without|no) (rules|limits|restrictions)",
        r"act as .*(unfiltered|uncensored|ungoverned)",
        r"bypass (safety|content|moderation|guard)(rails| policies| systems)?",
        r"say .* then (forget|ignore) (that|everything)",
    )
)


def redact_text(text: str) -> str:
    out = text
    for pattern, label in _REDACTORS:
        out = pattern.sub(label, out)
    return out


def redact_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    redacted: list[dict[str, Any]] = []
    for msg in messages:
        raw_content: Any = msg.get("content")
        if isinstance(raw_content, str):
            cleaned_content: Any = redact_text(raw_content)
        elif isinstance(raw_content, list):
            cleaned_content = redact_content_parts(raw_content)
        else:
            cleaned_content = raw_content
        redacted.append({**msg, "content": cleaned_content})
    return redacted


def redact_content_parts(parts: list[Any]) -> list[Any]:
    cleaned: list[Any] = []
    for part in parts:
        if isinstance(part, dict) and isinstance(part.get("text"), str):
            cleaned.append({**part, "text": redact_text(part["text"])})
        else:
            cleaned.append(part)
    return cleaned


def injection_score(text: str) -> int:
    score = 0
    for pattern in INJECTION_PATTERNS:
        score += len(pattern.findall(text))
    return score


def messages_contain_injection(messages: list[dict[str, Any]]) -> bool:
    for msg in messages:
        if msg.get("role") != "user":
            continue
        content = msg.get("content")
        if isinstance(content, str) and injection_score(content) > 0:
            return True
        if isinstance(content, list):
            texts = [
                part.get("text", "")
                for part in content
                if isinstance(part, dict) and isinstance(part.get("text"), str)
            ]
            if any(injection_score(text) > 0 for text in texts):
                return True
    return False
