import re
from datetime import datetime
from zoneinfo import ZoneInfo

from app.parsers.base import ParsedEvent, ParsingError

SYSLOG_RE = re.compile(r"^(?P<ts>[A-Z][a-z]{2}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2})\s+(?P<host>\S+)\s+(?P<process>[\w.-]+)(?:\[(?P<pid>\d+)\])?:\s+(?P<message>.+)$")
USER_RE = re.compile(r"(?:for (?:invalid user )?|user[ =])(?P<user>[\w.@-]+)", re.I)
IP_RE = re.compile(r"(?:from\s+|rhost=)(?P<ip>(?:\d{1,3}\.){3}\d{1,3}|[0-9a-f:]+)", re.I)


def parse_linux(line: str, *, year: int | None = None, server_timezone: str = "UTC") -> ParsedEvent:
    match = SYSLOG_RE.match(line)
    if not match:
        raise ParsingError("malformed Linux syslog line")
    message = match.group("message")
    lower = message.lower()
    action, outcome, category, severity, tags = "system_message", None, "system", "info", []
    if "failed password" in lower or "authentication failure" in lower:
        action, outcome, category, severity, tags = "login", "failure", "authentication", "medium", ["login_failed"]
    elif "accepted password" in lower or "accepted publickey" in lower or "session opened" in lower:
        action, outcome, category, severity, tags = "login", "success", "authentication", "info", ["login_success"]
    elif match.group("process") == "sudo" or "sudo:" in lower:
        action, category, severity, tags = "privilege_escalation", "authorization", "medium", ["sudo"]
        outcome = "failure" if "authentication failure" in lower or "not in the sudoers" in lower else "success"
    user_match, ip_match = USER_RE.search(message), IP_RE.search(message)
    ts_text = match.group("ts")
    try:
        assumed_year = year or datetime.now().year
        zone = ZoneInfo(server_timezone)
        normalized = datetime.strptime(f"{assumed_year} {ts_text}", "%Y %b %d %H:%M:%S").replace(tzinfo=zone)
    except (ValueError, KeyError) as exc:
        raise ParsingError("invalid Linux syslog timestamp") from exc
    return ParsedEvent(
        timestamp_original=ts_text, timestamp_normalized=normalized, timezone=server_timezone,
        source_type="linux_syslog", source_name=match.group("process"), host=match.group("host"),
        event_category=category, event_action=action, event_outcome=outcome, severity=severity,
        username=user_match.group("user") if user_match else None,
        source_ip=ip_match.group("ip") if ip_match else None, process_name=match.group("process"),
        parser_name="linux_syslog_regex", parser_confidence=0.80, tags=tags,
        timestamp_confidence=0.70,
        timestamp_assumptions=[f"year assumed from evidence upload: {assumed_year}", f"timezone assumed from server: {server_timezone}"],
        year_source="evidence_upload_timestamp", timezone_source="server_default",
    )
