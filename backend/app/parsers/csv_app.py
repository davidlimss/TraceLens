import csv
from io import StringIO

from app.parsers.base import ParsedEvent, ParsingError
from app.parsers.json_app import _first, _timestamp


def parse_csv_headers(line: str) -> list[str]:
    try:
        rows = list(csv.reader(StringIO(line), strict=True))
    except csv.Error as exc:
        raise ParsingError("malformed CSV header") from exc
    if len(rows) != 1 or not rows[0]:
        raise ParsingError("CSV header is missing")
    headers = [item.strip() for item in rows[0]]
    if any(not item for item in headers) or len(set(headers)) != len(headers):
        raise ParsingError("CSV headers must be non-empty and unique")
    return headers


def parse_csv_app(line: str, headers: list[str], *, server_timezone: str = "UTC") -> ParsedEvent:
    try:
        rows = list(csv.reader(StringIO(line), strict=True))
    except csv.Error as exc:
        raise ParsingError("malformed CSV application log") from exc
    if len(rows) != 1 or len(rows[0]) != len(headers):
        raise ParsingError("CSV row column count does not match header")
    data = dict(zip(headers, rows[0]))
    if not any(value.strip() for value in data.values()):
        raise ParsingError("CSV application log row is empty")
    ts = _first(data, "timestamp", "time", "@timestamp", "datetime")
    normalized, assumptions = _timestamp(ts, server_timezone)
    level = str(_first(data, "level", "severity", "log_level") or "info").lower()
    message = str(_first(data, "message", "msg", "event") or "")
    return ParsedEvent(
        timestamp_original=str(ts) if ts is not None else None,
        timestamp_normalized=normalized,
        timezone=(server_timezone if assumptions and ts is not None else (normalized.tzname() if normalized else None)),
        source_type="application_csv",
        source_name=str(_first(data, "service", "application", "logger") or "application"),
        host=_first(data, "host", "hostname"), event_category="application",
        event_action=str(_first(data, "action", "event_action") or "message"),
        event_outcome=_first(data, "outcome", "status"), severity=level,
        username=_first(data, "user", "username", "user_id"),
        source_ip=_first(data, "ip", "source_ip", "client_ip"),
        destination_ip=_first(data, "destination_ip", "server_ip"),
        process_name=_first(data, "process", "process_name"),
        file_name=_first(data, "file", "file_name"),
        parser_name="generic_csv_v1", parser_confidence=0.80,
        tags=["message_present"] if message else [],
        session_id=_first(data, "session", "session_id", "request_id"),
        timestamp_confidence=0.75 if assumptions else 1.0,
        timestamp_assumptions=assumptions,
        year_source="raw_event" if normalized else None,
        timezone_source="server_default" if assumptions and ts is not None else ("raw_event" if normalized else None),
    )
