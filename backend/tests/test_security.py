import base64
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.agent_tools import ToolRegistry, search_disconfirming_evidence
from app.auth import hash_password, require_case_permission, verify_password
from app.main import (build_formal_pdf_report, build_markdown_report, export_report, finding_recommendations,
                      get_event_context, get_log_status)
from app.models import AuditLog, Base, Case, CaseMembership, Event, EvidenceFile, User
from app.schemas import ReportExportRequest
from app.security import (FixedWindowRateLimiter, RateLimitExceeded, UploadValidationError,
                          safe_evidence_path, validate_filename, validate_mime_type,
                          validate_sample_and_detect, validate_size)


@pytest.fixture
def db():
    engine = create_engine("sqlite+pysqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def add_case(db: Session, name: str) -> Case:
    case = Case(name=name)
    db.add(case)
    db.commit()
    return case


def add_event(db: Session, case: Case, evidence: EvidenceFile) -> Event:
    event = Event(
        case_id=case.case_id, evidence_file_id=evidence.evidence_file_id,
        timestamp_original="2026-01-01T00:00:00Z", timestamp_normalized=datetime(2026, 1, 1, tzinfo=timezone.utc),
        timezone="UTC", source_type="application_json", source_name="app", host=None,
        event_category="application", event_action="message", event_outcome=None, severity="info",
        username=None, source_ip="192.0.2.1", destination_ip=None, process_name=None, file_name=None,
        raw_log='{"message":"safe"}', raw_line_number=1, parser_name="test", parser_confidence=1.0,
        tags=[], session_id=None, timestamp_confidence=1.0, timestamp_assumptions=[],
    )
    db.add(event)
    db.commit()
    return event


def add_evidence(db: Session, case: Case, identifier: uuid.UUID | None = None) -> EvidenceFile:
    evidence = EvidenceFile(evidence_file_id=identifier or uuid.uuid4(), case_id=case.case_id,
                            original_filename="safe.log", storage_path=f"/evidence/{uuid.uuid4()}",
                            sha256="0" * 64, size_bytes=10, detected_format="linux_syslog", status="parsed")
    db.add(evidence)
    db.commit()
    return evidence


@pytest.mark.parametrize("filename", ["../secret.log", "..\\secret.log", "/tmp/secret.log", "safe.log/../../x", "bad.exe", "\x00.log"])
def test_dangerous_or_unsupported_filename_is_rejected(filename):
    with pytest.raises(UploadValidationError):
        validate_filename(filename)


def test_supported_filename_mime_and_content_are_accepted():
    assert validate_filename("auth.log") == "auth.log"
    assert validate_filename("events.csv") == "events.csv"
    assert validate_filename("syslog") == "syslog"
    assert validate_mime_type("text/plain; charset=utf-8") == "text/plain"
    assert validate_mime_type("text/csv") == "text/csv"
    assert validate_sample_and_detect(b'{"timestamp":"2026-01-01T00:00:00Z","message":"ok"}\n') == "application_json"
    assert validate_sample_and_detect(
        b"timestamp,level,message,user,ip\n2026-01-01T00:00:00Z,info,ok,alice,192.0.2.1\n"
    ) == "application_csv"


def test_unsupported_mime_and_malformed_content_are_rejected():
    with pytest.raises(UploadValidationError, match="MIME"):
        validate_mime_type("application/x-msdownload")
    assert validate_sample_and_detect(b"not a supported log") == "generic_text"
    with pytest.raises(UploadValidationError, match="UTF-8"):
        validate_sample_and_detect(b"\xff\xfe")


def test_size_limit_fails_before_oversized_chunk_is_accepted():
    assert validate_size(5, 5, 10) == 10
    with pytest.raises(UploadValidationError) as error:
        validate_size(10, 1, 10)
    assert error.value.status_code == 413


def test_canonical_evidence_path_stays_under_storage(tmp_path):
    evidence_id = uuid.uuid4()
    path = safe_evidence_path(tmp_path, evidence_id)
    assert path.parent == tmp_path.resolve()
    assert path.name == str(evidence_id)


def test_fixed_window_rate_limit_blocks_after_limit():
    limiter = FixedWindowRateLimiter()
    assert limiter.check("chat:192.0.2.1", 2, 60, now=100) == 1
    assert limiter.check("chat:192.0.2.1", 2, 60, now=100) == 2
    with pytest.raises(RateLimitExceeded):
        limiter.check("chat:192.0.2.1", 2, 60, now=100)
    assert limiter.check("chat:192.0.2.1", 2, 60, now=200) == 1


def test_cross_case_event_evidence_and_agent_tool_access_are_denied(db):
    case_a, case_b = add_case(db, "A"), add_case(db, "B")
    evidence_b = add_evidence(db, case_b)
    event_b = add_event(db, case_b, evidence_b)

    with pytest.raises(HTTPException) as event_error:
        get_event_context(case_a.case_id, event_b.event_id, 5, _user=None, db=db)
    assert event_error.value.status_code == 404
    with pytest.raises(HTTPException) as evidence_error:
        get_log_status(case_a.case_id, evidence_b.evidence_file_id, _user=None, db=db)
    assert evidence_error.value.status_code == 404
    with pytest.raises(ValueError, match="active case"):
        ToolRegistry(db, case_a.case_id).execute("get_raw_evidence", {"event_id": str(event_b.event_id)})


def test_disconfirming_search_returns_benign_candidate_only_from_active_case(db):
    case = add_case(db, "maintenance")
    evidence = add_evidence(db, case)
    event = add_event(db, case, evidence)
    event.event_action = "maintenance"
    db.commit()

    result = search_disconfirming_evidence(
        db, case.case_id,
        {"hypothesis_id": "H-001", "entities": {"source_ip": "192.0.2.1"}},
    )
    assert result["search_purpose"] == "disconfirming_evidence"
    assert result["candidate_count"] == 1
    assert result["events"][0]["evidence_id"] == str(event.event_id)


def test_export_is_case_scoped_and_audited(db):
    case_a, case_b = add_case(db, "A"), add_case(db, "B")
    add_evidence(db, case_b)
    response = export_report(case_a.case_id, ReportExportRequest(format="markdown"),
                             user=SimpleNamespace(username="tester"), _csrf=None, db=db)
    assert response.format == "markdown"
    assert "## 1. Ringkasan Eksekutif" in response.content
    assert "## 6. Batasan" in response.content
    audit = db.scalar(select(AuditLog).where(AuditLog.case_id == case_a.case_id,
                                             AuditLog.action == "report_export_generated"))
    assert audit is not None
    assert audit.details["finding_count"] == 0


def test_markdown_report_includes_vigil_hypothesis_evidence_and_rejection_reason():
    case_id = uuid.uuid4()
    report = build_markdown_report(
        case_id,
        [],
        [],
        case_name="VIGIL report",
        investigation={
            "agent_run_id": "run-001",
            "question": "Investigate authentication activity",
            "status": "completed",
            "stop_reason": "VERIFICATION_FAILED",
            "plan": {"steps": [{"status": "completed", "objective": "Review timeline"}]},
            "hypotheses": [{
                "hypothesis_id": "H-001",
                "status": "weakened",
                "statement": "Activity may be password guessing",
                "supporting_evidence_ids": ["evidence-a"],
                "contradicting_evidence_ids": ["evidence-b"],
                "missing_evidence": ["maintenance ownership"],
                "alternative_explanations": ["authorized maintenance"],
            }],
            "evidence_gaps": [{"priority": "high", "description": "Need maintenance ticket"}],
            "verification_summary": {
                "verified_count": 0,
                "rejected_count": 1,
                "rejection_reasons": [{"reason_code": "INVALID_EVIDENCE", "detail": "Evidence is outside case"}],
            },
            "repair_state": {"attempt_count": 1},
        },
    )
    assert "### Hypothesis evidence links" in report
    assert "Supporting evidence: evidence-a" in report
    assert "Contradicting evidence: evidence-b" in report
    assert "Missing evidence: maintenance ownership" in report
    assert "Alternative explanations: authorized maintenance" in report
    assert "#### Verification rejection reasons" in report
    assert "INVALID_EVIDENCE" in report


def test_pdf_export_returns_real_pdf_bytes(db):
    case = add_case(db, "PDF case")
    response = export_report(case.case_id, ReportExportRequest(format="pdf"),
                             user=SimpleNamespace(username="tester"), _csrf=None, db=db)
    document = base64.b64decode(response.content)
    assert response.format == "pdf"
    assert document.startswith(b"%PDF-")
    assert len(document) > 1000


def test_formal_pdf_wraps_long_timeline_entities(db):
    case = add_case(db, "Formal report with long entities")
    evidence = add_evidence(db, case)
    event = add_event(db, case, evidence)
    event.source_ip = None
    event.source_name = r"C:\Users\research\AppData\Local\Programs\Ollama\a-very-long-component-name"
    event.event_action = "application_message_with_a_long_action_name"
    db.commit()
    document = build_formal_pdf_report(case, [], [evidence], [event] * 80)
    assert document.startswith(b"%PDF-")
    assert len(document) > 5000


def test_recommendations_are_specific_to_finding_type():
    brute_force = SimpleNamespace(finding_type="brute_force")
    successful = SimpleNamespace(finding_type="successful_login_after_failures")
    brute_text = " ".join(text for _, text in finding_recommendations(brute_force))
    success_text = " ".join(text for _, text in finding_recommendations(successful))
    assert "rate limiting" in brute_text
    assert "rotasi kredensial" in success_text
    assert "shared IP" in brute_text and "shared IP" in success_text


def test_password_hash_is_salted_and_verified():
    first, second = hash_password("correct horse"), hash_password("correct horse")
    assert first != second
    assert verify_password("correct horse", first)
    assert not verify_password("wrong", first)


def test_case_membership_enforces_authorization(db):
    case = add_case(db, "private")
    allowed = User(username="allowed", password_hash="x", global_role="user")
    denied = User(username="denied", password_hash="x", global_role="user")
    db.add_all([allowed, denied]); db.flush()
    db.add(CaseMembership(case_id=case.case_id, user_id=allowed.user_id, role="viewer")); db.commit()
    dependency = require_case_permission("read")
    assert dependency(case.case_id, db, allowed) is allowed
    with pytest.raises(HTTPException) as error:
        dependency(case.case_id, db, denied)
    assert error.value.status_code == 403
