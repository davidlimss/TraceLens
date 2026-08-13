import uuid
from datetime import datetime, timedelta, timezone

from app.engine import build_correlations, detect_auth_findings, detect_extended_findings, timeline_sort_key
from app.models import Event


CASE_ID = uuid.uuid4()


def event(*, minute: int, line: int, outcome: str, ip: str = "192.0.2.44", user: str = "root", evidence=None) -> Event:
    return Event(
        event_id=uuid.uuid4(), case_id=CASE_ID, evidence_file_id=evidence or uuid.uuid4(),
        timestamp_original=f"Jan 10 10:{minute:02d}:00",
        timestamp_normalized=datetime(2026, 1, 10, 10, minute, tzinfo=timezone.utc), timezone="UTC",
        source_type="linux_syslog", source_name="sshd", event_category="authentication",
        event_action="login", event_outcome=outcome, severity="medium", username=user,
        source_ip=ip, raw_log=f"line {line}", raw_line_number=line,
        parser_name="test", parser_confidence=1.0, tags=[], session_id=None,
        timestamp_confidence=1.0, timestamp_assumptions=[],
    )


def test_timeline_merges_files_and_uses_raw_line_as_timestamp_tie_breaker():
    timestamp = datetime(2026, 1, 10, 10, 0, tzinfo=timezone.utc)
    evidence = uuid.uuid4()
    first = event(minute=0, line=20, outcome="failure", evidence=evidence)
    second = event(minute=0, line=2, outcome="failure", evidence=evidence)
    first.timestamp_normalized = second.timestamp_normalized = timestamp
    assert sorted([first, second], key=timeline_sort_key) == [second, first]


def test_correlation_has_human_readable_reason():
    events = [event(minute=0, line=1, outcome="failure"), event(minute=4, line=2, outcome="failure")]
    correlations = build_correlations(events, window_minutes=5)
    ip_correlation = next(item for item in correlations if item.entity_type == "source_ip")
    assert ip_correlation.correlation_reason == "shared source_ip within 5 minutes (4.0 minutes apart)"
    assert ip_correlation.time_delta_seconds == 240


def test_correlation_deduplicates_retried_duplicate_events():
    first = event(minute=0, line=1, outcome="failure")
    second = event(minute=1, line=2, outcome="failure")
    correlations = build_correlations([first, second, first, second], window_minutes=5)
    keys = [(item.event_id, item.related_event_id, item.entity_type) for item in correlations]
    assert len(keys) == len(set(keys))


def test_brute_force_then_success_creates_high_risk_explainable_finding():
    evidence_a, evidence_b = uuid.uuid4(), uuid.uuid4()
    failures = [event(minute=minute, line=minute + 1, outcome="failure", evidence=evidence_a) for minute in range(5)]
    success = event(minute=6, line=1, outcome="success", evidence=evidence_b)
    events = [success, *reversed(failures)]
    correlations = build_correlations(events, window_minutes=10)
    findings = detect_auth_findings(events, correlations, threshold=5, window_minutes=10)

    assert {finding.finding_type for finding in findings} == {"brute_force", "successful_login_after_failures"}
    compromise = next(item for item in findings if item.finding_type == "successful_login_after_failures")
    assert 0.8 <= compromise.risk_score <= 1.0
    assert len(compromise.evidence_ids) == 6
    assert compromise.risk_breakdown["formula"].startswith("severity*0.3")
    components = compromise.risk_breakdown["components"]
    assert components["frequency"]["contribution"] == 0.2
    assert 0 < components["correlation"]["value"] <= 1
    assert compromise.risk_breakdown["risk_version"] == "risk-v1.1"


def test_events_outside_window_are_not_correlated():
    early = event(minute=0, line=1, outcome="failure")
    late = event(minute=0, line=2, outcome="failure")
    late.timestamp_normalized = early.timestamp_normalized + timedelta(minutes=16)
    assert build_correlations([early, late], window_minutes=15) == []


def test_dense_events_generate_linear_not_quadratic_correlations():
    base = datetime(2026, 1, 10, 10, 0, tzinfo=timezone.utc)
    events = []
    for index in range(2_000):
        item = event(minute=0, line=index + 1, outcome="failure")
        item.timestamp_normalized = base + timedelta(seconds=index)
        events.append(item)
    correlations = build_correlations(events, window_minutes=10)
    # Each adjacent pair can link once by source_ip and once by username.
    assert len(correlations) <= (len(events) - 1) * 3


def test_password_spray_and_distributed_guessing_are_mapped_to_mitre():
    spray = [event(minute=i, line=i+1, outcome="failure", ip="198.51.100.10", user=f"user{i}") for i in range(5)]
    distributed = [event(minute=i, line=20+i, outcome="failure", ip=f"203.0.113.{i+1}", user="admin") for i in range(5)]
    findings = detect_extended_findings([*spray, *distributed], threshold=5, window_minutes=10)
    mapped = {item.finding_type: item for item in findings}
    assert mapped["password_spraying"].mitre_technique == "T1110.003"
    assert mapped["distributed_password_guessing"].mitre_technique == "T1110.001"
    assert mapped["password_spraying"].confidence_score >= .8


def test_signature_rules_include_false_positive_guidance():
    powershell = event(minute=0, line=1, outcome="success")
    powershell.event_action = "process_create"; powershell.event_category = "process"
    powershell.command_line = "powershell.exe -EncodedCommand SQBFAFgA"
    web = event(minute=1, line=2, outcome="failure")
    web.event_action = "get"; web.event_category = "web"; web.url_path = "/../../etc/passwd"
    types = {item.finding_type: item for item in detect_extended_findings([powershell, web], threshold=5, window_minutes=10)}
    assert types["suspicious_powershell"].mitre_technique == "T1059.001"
    assert types["web_exploitation"].mitre_technique == "T1190"
    assert types["web_exploitation"].false_positive_considerations
