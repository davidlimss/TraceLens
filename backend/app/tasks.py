import uuid
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
import hashlib
import redis
from pathlib import Path
from sqlalchemy import select

from app.database import SessionLocal
from app.config import get_settings
from app.engine import rebuild_case_analysis
from app.models import AgentRun, AuditLog, Event, EvidenceFile, QuarantinedLine
from app.parsers import detect_format, parse_line
from app.parsers.base import ParsingError
from app.parsers.csv_app import parse_csv_app, parse_csv_headers
from app.worker import celery_app

PARSER_VERSION = "1.1.0"
settings = get_settings()


def _progress(evidence_file_id: uuid.UUID, processed: int, parsed: int, malformed: int, total: int) -> None:
    with SessionLocal() as progress_db:
        evidence = progress_db.get(EvidenceFile, evidence_file_id)
        if evidence is None:
            return
        evidence.processed_lines, evidence.parsed_events, evidence.malformed_lines = processed, parsed, malformed
        evidence.progress_percent = min(99, int(processed / max(total, 1) * 100))
        evidence.heartbeat_at = datetime.now(timezone.utc)
        progress_db.commit()


@celery_app.task(name="parse_evidence_file")
def parse_evidence_file(evidence_file_id: str) -> dict:
    evidence_uuid = uuid.UUID(evidence_file_id)
    with SessionLocal() as db:
        evidence = db.get(EvidenceFile, evidence_uuid)
        if evidence is None:
            raise ValueError("evidence file not found")
        evidence.status = "parsing"
        evidence.heartbeat_at = datetime.now(timezone.utc)
        db.commit()
        try:
            path = Path(evidence.storage_path)
            with path.open("r", encoding="utf-8", errors="strict") as handle:
                lines = handle.read().splitlines()
            detected = detect_format(lines)
            events = []
            quarantined = []
            total_nonempty = sum(bool(line.strip()) for line in lines)
            evidence.total_lines = total_nonempty
            db.commit()
            csv_headers = None
            processed = 0
            for line_number, raw_line in enumerate(lines, 1):
                if not raw_line.strip():
                    continue
                if detected == "application_csv" and csv_headers is None:
                    csv_headers = parse_csv_headers(raw_line)
                    processed += 1
                    continue
                try:
                    parsed = (parse_csv_app(raw_line, csv_headers, server_timezone=settings.server_timezone)
                              if detected == "application_csv" else
                              parse_line(detected, raw_line, upload_year=evidence.uploaded_at.year,
                                         server_timezone=settings.server_timezone))
                except ParsingError as exc:
                    if evidence.parsing_mode != "quarantine":
                        raise
                    quarantined.append(QuarantinedLine(
                        case_id=evidence.case_id, evidence_file_id=evidence.evidence_file_id,
                        raw_log=raw_line, raw_line_number=line_number,
                        reason_code="parse_error", error_message=str(exc),
                    ))
                    processed += 1
                    if processed % 500 == 0:
                        _progress(evidence_uuid, processed, len(events), len(quarantined), total_nonempty)
                    continue
                events.append(Event(
                    case_id=evidence.case_id, evidence_file_id=evidence.evidence_file_id,
                    raw_log=raw_line, raw_line_number=line_number, **asdict(parsed)
                ))
                processed += 1
                if processed % 500 == 0:
                    _progress(evidence_uuid, processed, len(events), len(quarantined), total_nonempty)
            evidence.detected_format = detected
            evidence.status = "parsed_with_warnings" if quarantined else "parsed"
            evidence.parsed_at = datetime.now(timezone.utc)
            evidence.processed_lines, evidence.parsed_events = total_nonempty, len(events)
            evidence.malformed_lines, evidence.progress_percent = len(quarantined), 100
            evidence.heartbeat_at = evidence.parsed_at
            evidence.completeness_ratio = len(events) / max(total_nonempty - (1 if detected == "application_csv" else 0), 1)
            db.add_all([*events, *quarantined])
            db.flush()
            lock = redis.Redis.from_url(settings.redis_url).lock(
                f"tracelens:case:{evidence.case_id}:analysis", timeout=300, blocking_timeout=60
            )
            if not lock.acquire(blocking=True):
                raise RuntimeError("could not acquire per-case analysis lock")
            try:
                correlation_count, finding_count = rebuild_case_analysis(db, evidence.case_id, settings)
            finally:
                lock.release()
            db.add(AuditLog(case_id=evidence.case_id, evidence_file_id=evidence.evidence_file_id,
                            action="evidence_parsed", parser_version=PARSER_VERSION,
                            details={"format": detected, "event_count": len(events),
                                     "correlation_count": correlation_count, "finding_count": finding_count,
                                     "parsing_mode": evidence.parsing_mode, "malformed_lines": len(quarantined),
                                     "completeness_ratio": evidence.completeness_ratio,
                                     "correlation_window_minutes": settings.correlation_window_minutes}))
            db.commit()
            return {"format": detected, "event_count": len(events)}
        except Exception as exc:
            db.rollback()
            evidence = db.get(EvidenceFile, evidence_uuid)
            evidence.status = "failed"
            evidence.error_message = str(exc)
            evidence.heartbeat_at = datetime.now(timezone.utc)
            db.add(AuditLog(case_id=evidence.case_id, evidence_file_id=evidence.evidence_file_id,
                            action="evidence_parsing_failed", parser_version=PARSER_VERSION,
                            details={"error": str(exc)}))
            db.commit()
            raise


@celery_app.task(name="mark_stuck_jobs")
def mark_stuck_jobs() -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=settings.stuck_job_minutes)
    with SessionLocal() as db:
        rows = list(db.scalars(select(EvidenceFile).where(EvidenceFile.status == "parsing",
                                                          EvidenceFile.heartbeat_at < cutoff)))
        for evidence in rows:
            evidence.status = "stuck"
            db.add(AuditLog(case_id=evidence.case_id, evidence_file_id=evidence.evidence_file_id,
                            action="evidence_parsing_stuck", parser_version=PARSER_VERSION,
                            details={"heartbeat_at": evidence.heartbeat_at.isoformat() if evidence.heartbeat_at else None}))
        db.commit()
        return len(rows)


@celery_app.task(name="mark_stuck_agent_runs")
def mark_stuck_agent_runs() -> int:
    """Fail-closed runs whose worker heartbeat stopped before a checkpoint."""
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=settings.agent_stuck_minutes)
    with SessionLocal() as db:
        rows = list(db.scalars(select(AgentRun).where(
            AgentRun.status == "running", AgentRun.updated_at < cutoff,
        )))
        for run in rows:
            last_checkpoint = run.updated_at
            run.status = "failed"
            run.stop_reason = "agent_worker_heartbeat_expired"
            run.updated_at = datetime.now(timezone.utc)
            db.add(AuditLog(case_id=run.case_id, action="agent_run_stuck", actor="scheduler",
                            model_version=run.model_version, prompt_version=run.prompt_version,
                            details={"agent_run_id": str(run.agent_run_id),
                                     "last_checkpoint_at": last_checkpoint.isoformat() if last_checkpoint else None,
                                     "agent_stuck_minutes": settings.agent_stuck_minutes}))
        db.commit()
        return len(rows)


@celery_app.task(name="verify_evidence_files")
def verify_evidence_files() -> dict:
    checked = mismatches = 0
    with SessionLocal() as db:
        evidence_files = list(db.scalars(select(EvidenceFile).where(
            EvidenceFile.status.in_(["parsed", "parsed_with_warnings"])
        )))
        for evidence in evidence_files:
            digest = hashlib.sha256()
            with Path(evidence.storage_path).open("rb") as handle:
                while chunk := handle.read(1024 * 1024):
                    digest.update(chunk)
            actual = digest.hexdigest(); checked += 1
            evidence.integrity_status = "match" if actual == evidence.sha256 else "mismatch"
            evidence.integrity_verified_at = datetime.now(timezone.utc)
            mismatches += evidence.integrity_status == "mismatch"
            db.add(AuditLog(case_id=evidence.case_id, evidence_file_id=evidence.evidence_file_id,
                            action="evidence_integrity_verified", parser_version=PARSER_VERSION,
                            details={"expected_sha256": evidence.sha256, "actual_sha256": actual,
                                     "status": evidence.integrity_status, "periodic": True}))
        db.commit()
    return {"checked": checked, "mismatches": mismatches}
