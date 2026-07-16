from app.parsers.access import parse_access
from app.parsers.base import ParsedEvent
from app.parsers.json_app import parse_json_app
from app.parsers.linux import parse_linux
from app.parsers.logfmt import parse_logfmt
from app.parsers.text import parse_text


def parse_line(format_name: str, line: str, *, upload_year: int | None = None, server_timezone: str = "UTC") -> ParsedEvent:
    parsers = {"linux_syslog": parse_linux, "web_access": parse_access, "application_json": parse_json_app,
               "application_logfmt": parse_logfmt, "generic_text": parse_text}
    try:
        parser = parsers[format_name]
    except KeyError as exc:
        raise ValueError(f"unsupported format: {format_name}") from exc
    if format_name == "linux_syslog":
        return parser(line, year=upload_year, server_timezone=server_timezone)
    if format_name in {"application_json", "application_logfmt", "generic_text"}:
        return parser(line, server_timezone=server_timezone)
    return parser(line)
