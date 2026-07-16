import json
import re

from app.parsers.base import ParsedEvent, ParsingError
from app.parsers.json_app import _timestamp


LOGFMT_PAIR_RE = re.compile(r'(?:^|\s)([A-Za-z_][\w.-]*)=("(?:[^"\\]|\\.)*"|\S+)')


def parse_logfmt_values(line: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for key, raw in LOGFMT_PAIR_RE.findall(line):
        if raw.startswith('"'):
            try:
                raw = json.loads(raw)
            except json.JSONDecodeError:
                raw = raw[1:-1]
        values[key] = str(raw)
    return values


def parse_logfmt(line: str, *, server_timezone: str = "UTC") -> ParsedEvent:
    data = parse_logfmt_values(line)
    if len(data) < 2:
        raise ParsingError("malformed logfmt line")
    ts = data.get("time") or data.get("timestamp") or data.get("ts") or data.get("datetime")
    normalized, assumptions = _timestamp(ts, server_timezone)
    message = data.get("msg") or data.get("message") or data.get("event") or ""
    lower = message.lower()
    action = data.get("action") or "message"
    outcome = data.get("outcome") or data.get("status")
    category = data.get("category") or "application"
    tags = ["logfmt"]
    if "login" in lower or "authentication" in lower:
        category, action = "authentication", "login"
        if any(term in lower for term in ("failed", "failure", "denied", "invalid")):
            outcome, tags = "failure", tags + ["login_failed"]
        elif any(term in lower for term in ("success", "accepted", "authenticated")):
            outcome, tags = "success", tags + ["login_success"]
    return ParsedEvent(
        timestamp_original=ts, timestamp_normalized=normalized,
        timezone=(server_timezone if assumptions and ts else (normalized.tzname() if normalized else None)),
        source_type="application_logfmt", source_name=data.get("service") or data.get("app") or "application",
        host=data.get("host") or data.get("hostname"), event_category=category, event_action=action,
        event_outcome=outcome, severity=(data.get("level") or data.get("severity") or "info").lower(),
        username=data.get("user") or data.get("username"),
        source_ip=data.get("src_ip") or data.get("source_ip") or data.get("client_ip") or data.get("ip"),
        destination_ip=data.get("dst_ip") or data.get("destination_ip") or data.get("server_ip"),
        process_name=data.get("process") or data.get("source"), file_name=data.get("file"),
        parser_name="generic_logfmt_v1", parser_confidence=0.82, tags=tags,
        session_id=data.get("session") or data.get("session_id") or data.get("request_id"),
        timestamp_confidence=0.75 if assumptions else 1.0, timestamp_assumptions=assumptions,
        year_source="raw_event" if normalized else None,
        timezone_source="server_default" if assumptions and ts else ("raw_event" if normalized else None),
    )
