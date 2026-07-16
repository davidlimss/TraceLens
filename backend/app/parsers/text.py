import re

from app.parsers.base import ParsedEvent, ParsingError
from app.parsers.json_app import _timestamp


ISO_PREFIX_RE = re.compile(r"^\[?(?P<ts>\d{4}-\d{2}-\d{2}[T ][0-9:.]+(?:Z|[+-]\d{2}:?\d{2})?)\]?\s*(?P<message>.*)$")
IP_RE = re.compile(r"(?<![\d.])((?:\d{1,3}\.){3}\d{1,3})(?![\d.])")


def parse_text(line: str, *, server_timezone: str = "UTC") -> ParsedEvent:
    text = line.strip()
    if not text:
        raise ParsingError("empty plain-text log line")
    match = ISO_PREFIX_RE.match(text)
    ts = match.group("ts") if match else None
    message = match.group("message") if match else text
    normalized, assumptions = _timestamp(ts, server_timezone)
    lower = message.lower()
    category, action, outcome, severity, tags = "generic", "message", None, "info", ["generic_text_fallback"]
    if "login" in lower or "password" in lower or "authentication" in lower:
        category, action = "authentication", "login"
        if any(term in lower for term in ("failed", "failure", "denied", "invalid")):
            outcome, severity, tags = "failure", "medium", tags + ["login_failed"]
        elif any(term in lower for term in ("success", "accepted", "authenticated")):
            outcome, tags = "success", tags + ["login_success"]
    ip_match = IP_RE.search(message)
    return ParsedEvent(
        timestamp_original=ts, timestamp_normalized=normalized,
        timezone=(server_timezone if assumptions and ts else (normalized.tzname() if normalized else None)),
        source_type="generic_text", source_name="plain_text", event_category=category,
        event_action=action, event_outcome=outcome, severity=severity,
        source_ip=ip_match.group(1) if ip_match else None,
        parser_name="generic_text_v1", parser_confidence=0.35, tags=tags,
        timestamp_confidence=0.50 if assumptions else 1.0, timestamp_assumptions=assumptions,
        year_source="raw_event" if normalized else None,
        timezone_source="server_default" if assumptions and ts else ("raw_event" if normalized else None),
    )
