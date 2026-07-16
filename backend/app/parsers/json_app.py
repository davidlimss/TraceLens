import json
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from app.parsers.base import ParsedEvent, ParsingError


def _first(data: dict, *keys: str):
    return next((data[key] for key in keys if key in data and data[key] not in (None, "")), None)


def _path(data: dict, *keys: str):
    for key in keys:
        current = data
        for part in key.split("."):
            if not isinstance(current, dict) or part not in current:
                current = None
                break
            current = current[part]
        if current not in (None, ""):
            return current
    return None


def _timestamp(value, server_timezone: str) -> tuple[datetime | None, list[str]]:
    if value is None:
        return None, ["timestamp missing"]
    text = str(value)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=ZoneInfo(server_timezone)), [f"timezone assumed from server: {server_timezone}"]
        return parsed, []
    except (ValueError, KeyError) as exc:
        raise ParsingError("invalid JSON application timestamp") from exc


def _int_or_none(value):
    try:
        return int(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def parse_json_app(line: str, *, server_timezone: str = "UTC") -> ParsedEvent:
    try:
        data = json.loads(line)
    except json.JSONDecodeError as exc:
        raise ParsingError("malformed JSON application log") from exc
    if not isinstance(data, dict):
        raise ParsingError("JSON application log must be an object")
    if not data:
        raise ParsingError("JSON application log object is empty")
    ts = _path(data, "timestamp", "time", "@timestamp", "datetime", "eventTime", "TimeCreated.SystemTime")
    normalized, assumptions = _timestamp(ts, server_timezone)
    level = str(_path(data, "level", "severity", "log.level", "log_level", "event.severity") or "info").lower()
    message = str(_first(data, "message", "msg", "event") or "")
    event_id = str(_path(data, "eventid", "event.code", "event.action", "event_id", "EventID",
                         "Event.System.EventID", "winlog.event_id", "eventName") or "")
    action = str(_path(data, "action", "event_action", "event.action") or event_id or "message")
    outcome = _path(data, "outcome", "status", "event.outcome")
    category = str(_path(data, "category", "event_category", "event.category") or "application")
    tags = ["message_present"] if message else []
    if event_id in {"cowrie.login.failed", "cowrie.login.success"}:
        category, action = "authentication", "login"
        outcome = "failure" if event_id.endswith("failed") else "success"
        tags.append("login_failed" if outcome == "failure" else "login_success")
    elif event_id.startswith("cowrie.command"):
        category, action, tags = "process", "command", tags + ["cowrie_command"]
    elif event_id in {"4624", "4625"}:
        category, action = "authentication", "login"
        outcome = "success" if event_id == "4624" else "failure"
        tags += ["windows_security", "login_success" if outcome == "success" else "login_failed"]
    elif event_id in {"1", "4688"} and _path(data, "CommandLine", "command_line", "process.command_line"):
        category, action, tags = "process", "process_create", tags + ["process_creation"]
    elif event_id in {"11"} and _path(data, "TargetFilename", "file.path"):
        category, action, tags = "file", "file_create", tags + ["file_creation"]
    elif event_id in {"7045", "4697"}:
        category, action, outcome, level = "persistence", "service_install", outcome or "success", "high"
        tags += ["service_install"]
    elif _path(data, "eventName"):
        category, action, tags = "cloud", str(_path(data, "eventName")), tags + ["cloud_audit"]
        outcome = "failure" if _path(data, "errorCode", "errorMessage") else (outcome or "success")
    elif _path(data, "event_type") == "alert":
        category, action, tags = "network", "alert", tags + ["suricata_alert"]
        level = str(_path(data, "alert.severity") or level)
    return ParsedEvent(
        timestamp_original=str(ts) if ts is not None else None, timestamp_normalized=normalized,
        timezone=(server_timezone if assumptions and ts is not None else (normalized.tzname() if normalized else None)), source_type="application_json",
        source_name=str(_path(data, "service", "application", "logger", "source", "sensor", "agent.name") or "application"),
        host=_path(data, "host", "hostname", "host.name", "computer", "Computer"), event_category=category,
        event_action=action, event_outcome=outcome, severity=level,
        username=_path(data, "user", "username", "user_id", "user.name", "User", "TargetUserName",
                       "userIdentity.userName", "userIdentity.arn"),
        source_ip=_path(data, "ip", "source_ip", "src_ip", "client_ip", "source.ip", "SourceIp",
                        "IpAddress", "sourceIPAddress"),
        destination_ip=_path(data, "destination_ip", "dst_ip", "server_ip", "destination.ip", "DestinationIp"),
        process_name=_path(data, "process", "process_name", "process.name", "Image", "NewProcessName"),
        file_name=_path(data, "file", "file_name", "file.name", "file.path", "TargetFilename"),
        parser_name="generic_json_v2", parser_confidence=0.92 if event_id.startswith("cowrie.") else 0.85,
        tags=tags, session_id=_path(data, "session", "session_id", "request_id", "session.id"),
        timestamp_confidence=0.75 if assumptions else 1.0, timestamp_assumptions=assumptions,
        year_source="raw_event" if normalized else None,
        timezone_source="server_default" if assumptions and ts is not None else ("raw_event" if normalized else None),
        event_code=event_id or None,
        command_line=_path(data, "command_line", "CommandLine", "process.command_line", "ProcessCommandLine"),
        parent_process_name=_path(data, "parent_process_name", "ParentImage", "process.parent.name"),
        source_port=_int_or_none(_path(data, "source_port", "src_port", "source.port", "SourcePort")),
        destination_port=_int_or_none(_path(data, "destination_port", "dest_port", "dst_port",
                                            "destination.port", "DestinationPort")),
        protocol=_path(data, "protocol", "proto", "network.transport"),
        http_method=_path(data, "http_method", "http.request.method", "request.method"),
        http_status=_int_or_none(_path(data, "http_status", "http.response.status_code", "status_code")),
        url_path=_path(data, "url", "url.path", "uri", "request.uri"),
        user_agent=_path(data, "user_agent", "user_agent.original", "http.user_agent"),
        file_hash=_path(data, "file_hash", "hash", "Hashes", "file.hash.sha256"),
    )
