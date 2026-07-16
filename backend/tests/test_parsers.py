import pytest

from app.parsers.access import parse_access
from app.parsers.base import ParsingError
from app.parsers.csv_app import parse_csv_app, parse_csv_headers
from app.parsers.detector import FormatDetectionError, detect_format
from app.parsers.json_app import parse_json_app
from app.parsers.linux import parse_linux
from app.parsers.logfmt import parse_logfmt
from app.parsers.text import parse_text


class TestLinuxParser:
    def test_valid_failed_login(self):
        event = parse_linux("Jan 10 10:20:30 server sshd[123]: Failed password for alice from 192.0.2.10 port 22 ssh2", year=2025)
        assert (event.event_outcome, event.username, event.source_ip) == ("failure", "alice", "192.0.2.10")

    def test_missing_optional_user_and_ip(self):
        event = parse_linux("Jan 10 10:20:30 server systemd[1]: Started Daily Cleanup.", year=2025)
        assert event.username is None and event.source_ip is None

    def test_malformed_is_explicit(self):
        with pytest.raises(ParsingError, match="malformed Linux"):
            parse_linux("this is not syslog")


class TestAccessParser:
    def test_valid_combined(self):
        event = parse_access('192.0.2.1 - bob [10/Oct/2000:13:55:36 -0700] "GET /index.html HTTP/1.1" 200 2326 "-" "Mozilla/5.0"')
        assert event.username == "bob" and event.event_outcome == "success"

    def test_missing_optional_fields(self):
        event = parse_access('192.0.2.1 - - [10/Oct/2000:13:55:36 -0700] "GET / HTTP/1.1" 404 -')
        assert event.username is None and event.event_outcome == "failure"

    def test_malformed_is_explicit(self):
        with pytest.raises(ParsingError, match="malformed Nginx/Apache"):
            parse_access("broken access line")


class TestJsonParser:
    def test_valid_json(self):
        event = parse_json_app('{"timestamp":"2025-01-01T00:00:00Z","level":"warning","message":"login","user":"alice","ip":"192.0.2.3"}')
        assert event.username == "alice" and event.severity == "warning"

    def test_missing_optional_fields(self):
        event = parse_json_app('{"message":"started"}')
        assert event.timestamp_normalized is None and event.username is None
        assert event.timestamp_assumptions == ["timestamp missing"]

    def test_malformed_is_explicit(self):
        with pytest.raises(ParsingError, match="malformed JSON"):
            parse_json_app('{"message":')


class TestCsvParser:
    headers = parse_csv_headers("timestamp,level,message,user,ip")

    def test_valid_csv(self):
        event = parse_csv_app('2025-01-01T00:00:00Z,warning,"login failed",alice,192.0.2.3', self.headers)
        assert event.username == "alice" and event.source_ip == "192.0.2.3"
        assert event.source_type == "application_csv"

    def test_missing_optional_fields(self):
        event = parse_csv_app(',,started,,', self.headers)
        assert event.timestamp_normalized is None and event.username is None
        assert event.timestamp_assumptions == ["timestamp missing"]

    def test_malformed_row_is_explicit(self):
        with pytest.raises(ParsingError, match="column count"):
            parse_csv_app("2025-01-01T00:00:00Z,info,missing-columns", self.headers)


def test_detection_uses_content():
    assert detect_format(['{"message":"hello"}']) == "application_json"
    assert detect_format(["timestamp,level,message,user,ip", "2025-01-01T00:00:00Z,info,login,alice,192.0.2.3"]) == "application_csv"
    assert detect_format(["unknown content"]) == "generic_text"
    assert detect_format(['time=2025-09-30T20:00:59-04:00 level=INFO msg="starting Ollama"']) == "application_logfmt"


def test_cowrie_json_maps_authentication_fields():
    event = parse_json_app('{"eventid":"cowrie.login.failed","timestamp":"2026-01-01T00:00:00Z",'
                           '"username":"root","src_ip":"192.0.2.9","session":"abc"}')
    assert (event.event_category, event.event_action, event.event_outcome) == ("authentication", "login", "failure")
    assert event.source_ip == "192.0.2.9" and event.session_id == "abc"


def test_logfmt_and_generic_text_are_ingestable():
    logfmt = parse_logfmt('time=2025-09-30T20:00:59-04:00 level=INFO source=app.go:1 msg="starting Ollama"')
    assert logfmt.source_type == "application_logfmt" and logfmt.timestamp_normalized is not None
    text = parse_text('2026-01-01T00:00:00Z authentication failed from 192.0.2.4')
    assert text.event_outcome == "failure" and text.source_ip == "192.0.2.4"


def test_windows_security_and_cloudtrail_are_normalized():
    windows = parse_json_app('{"@timestamp":"2026-01-01T00:00:00Z","EventID":4625,'
                             '"TargetUserName":"admin","IpAddress":"192.0.2.8"}')
    assert (windows.event_action, windows.event_outcome, windows.event_code) == ("login", "failure", "4625")
    cloud = parse_json_app('{"eventTime":"2026-01-01T00:00:00Z","eventName":"ConsoleLogin",'
                           '"sourceIPAddress":"198.51.100.5","userIdentity":{"userName":"alice"}}')
    assert cloud.event_category == "cloud" and cloud.source_ip == "198.51.100.5"
    assert cloud.username == "alice" and cloud.event_code == "ConsoleLogin"


def test_linux_missing_year_and_timezone_are_explicit_assumptions():
    event = parse_linux("Jan 10 10:20:30 server sshd[123]: Accepted password for alice from 192.0.2.10 port 22 ssh2",
                        year=2024, server_timezone="Asia/Jakarta")
    assert event.timestamp_normalized.year == 2024
    assert event.timestamp_confidence < 1
    assert event.timestamp_assumptions == ["year assumed from evidence upload: 2024", "timezone assumed from server: Asia/Jakarta"]


def test_json_naive_timestamp_uses_server_timezone_explicitly():
    event = parse_json_app('{"timestamp":"2025-01-01T00:00:00","message":"started"}', server_timezone="Asia/Jakarta")
    assert event.timestamp_confidence < 1
    assert event.timestamp_assumptions == ["timezone assumed from server: Asia/Jakarta"]


def test_large_json_log_is_parsed_deterministically():
    lines = [f'{{"timestamp":"2026-01-01T00:00:{index % 60:02d}Z","message":"event {index}","user":"user-{index % 10}"}}'
             for index in range(20_000)]
    assert detect_format(lines[:20]) == "application_json"
    events = [parse_json_app(line) for line in lines]
    assert len(events) == 20_000
    assert events[0].username == "user-0"
    assert events[-1].username == "user-9"
