from dataclasses import dataclass, field
from datetime import datetime


class ParsingError(ValueError):
    pass


@dataclass(slots=True)
class ParsedEvent:
    timestamp_original: str | None
    timestamp_normalized: datetime | None
    timezone: str | None
    source_type: str
    source_name: str
    event_category: str
    event_action: str
    severity: str = "info"
    event_outcome: str | None = None
    host: str | None = None
    username: str | None = None
    source_ip: str | None = None
    destination_ip: str | None = None
    process_name: str | None = None
    file_name: str | None = None
    parser_name: str = "unknown"
    parser_confidence: float = 0.0
    tags: list[str] = field(default_factory=list)
    session_id: str | None = None
    timestamp_confidence: float = 1.0
    timestamp_assumptions: list[str] = field(default_factory=list)
    year_source: str | None = None
    timezone_source: str | None = None
    event_code: str | None = None
    command_line: str | None = None
    parent_process_name: str | None = None
    source_port: int | None = None
    destination_port: int | None = None
    protocol: str | None = None
    http_method: str | None = None
    http_status: int | None = None
    url_path: str | None = None
    user_agent: str | None = None
    file_hash: str | None = None
