import re
from datetime import datetime

from app.parsers.base import ParsedEvent, ParsingError

ACCESS_RE = re.compile(r'^(?P<ip>\S+)\s+\S+\s+(?P<user>\S+)\s+\[(?P<ts>[^]]+)\]\s+"(?P<method>[A-Z]+)\s+(?P<path>\S+)(?:\s+(?P<protocol>[^"]+))?"\s+(?P<status>\d{3})\s+(?P<size>\S+)(?:\s+"(?P<referer>[^"]*)"\s+"(?P<agent>[^"]*)")?$')


def parse_access(line: str) -> ParsedEvent:
    match = ACCESS_RE.match(line)
    if not match:
        raise ParsingError("malformed Nginx/Apache combined access line")
    ts_text = match.group("ts")
    try:
        normalized = datetime.strptime(ts_text, "%d/%b/%Y:%H:%M:%S %z")
    except ValueError as exc:
        raise ParsingError("invalid access-log timestamp") from exc
    status = int(match.group("status"))
    outcome = "success" if status < 400 else "failure"
    severity = "medium" if status >= 500 else "low" if status >= 400 else "info"
    return ParsedEvent(
        timestamp_original=ts_text, timestamp_normalized=normalized, timezone=normalized.strftime("%z"),
        source_type="web_access", source_name="http_access", event_category="web",
        event_action=match.group("method").lower(), event_outcome=outcome, severity=severity,
        username=None if match.group("user") == "-" else match.group("user"), source_ip=match.group("ip"),
        file_name=match.group("path"), parser_name="combined_access_regex", parser_confidence=0.98,
        tags=[f"http_status:{status}"],
        year_source="raw_event", timezone_source="raw_event",
        protocol=match.group("protocol"), http_method=match.group("method"),
        http_status=status, url_path=match.group("path"), user_agent=match.group("agent"),
    )
