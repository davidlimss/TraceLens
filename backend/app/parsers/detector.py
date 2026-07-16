import json
import csv

from app.parsers.access import ACCESS_RE
from app.parsers.linux import SYSLOG_RE
from app.parsers.logfmt import parse_logfmt_values


class FormatDetectionError(ValueError):
    pass


def detect_format(lines: list[str]) -> str:
    samples = [line.strip() for line in lines if line.strip()][:20]
    if not samples:
        raise FormatDetectionError("file contains no non-empty log lines")
    scores = {"linux_syslog": 0, "web_access": 0, "application_json": 0, "application_csv": 0,
              "application_logfmt": 0}
    for line in samples:
        scores["linux_syslog"] += bool(SYSLOG_RE.match(line))
        scores["web_access"] += bool(ACCESS_RE.match(line))
        try:
            scores["application_json"] += isinstance(json.loads(line), dict)
        except (json.JSONDecodeError, TypeError):
            pass
        scores["application_logfmt"] += len(parse_logfmt_values(line)) >= 2
    try:
        header = [item.strip().lower() for item in next(csv.reader([samples[0]]))]
        known = {"timestamp", "time", "@timestamp", "datetime", "level", "severity", "message", "msg",
                 "event", "user", "username", "ip", "source_ip", "client_ip"}
        if len(samples) >= 2 and len(header) >= 2 and known.intersection(header):
            valid_rows = sum(len(next(csv.reader([line]))) == len(header) for line in samples[1:])
            scores["application_csv"] = valid_rows + 1
    except (csv.Error, StopIteration):
        pass
    detected, score = max(scores.items(), key=lambda item: item[1])
    if score == 0 or score / len(samples) < 0.5:
        # Valid UTF-8 line-oriented evidence is retained with explicitly low-confidence parsing.
        return "generic_text"
    return detected
