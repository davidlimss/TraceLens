import base64
import hashlib
import codecs
import html
import json
import os
import time
import uuid
from collections import Counter
from io import BytesIO
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, Request, Response, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, or_, select, text
from sqlalchemy.orm import Session
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.graphics.shapes import Drawing, Rect, String
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from prometheus_client import CONTENT_TYPE_LATEST, Counter as PromCounter, Gauge, Histogram, generate_latest

from app.config import get_settings
from app.database import Base, engine, get_db
from app.models import AuditLog, Case, CaseMembership, Correlation, Event, EvidenceFile, Finding, User, UserSession
from app.llm_gateway import AgentRuntimeError, LLMGateway, PROMPT_VERSION
from app.schemas import (CaseCreate, CaseRead, ChatRequest, ChatResponse, EntityRead, EventContext, EventPage,
                         CurrentUserRead, EventRead, EvidenceRead, FindingRead, FindingWorkflowUpdate, IntegrityVerificationRead, LoginRequest, ReportExportRequest, ReportExportResponse,
                         TimelineItem, TimelinePage)
from app.auth import (CSRF_COOKIE, SESSION_COOKIE, create_session, get_current_user, hash_password,
                      require_case_permission, require_csrf, token_hash, verify_password)
from app.security import (FixedWindowRateLimiter, RateLimitExceeded, UploadValidationError, safe_evidence_path,
                          validate_filename, validate_mime_type, validate_text_and_detect)
from app.security import validate_size
from app.tasks import parse_evidence_file
from app.engine import (RISK_THRESHOLD_VERSION, RISK_VERSION, TIMELINE_SORT_VERSION,
                        rebuild_case_analysis, timeline_order_by)
from app.agent_tools import TOOL_SCHEMA_VERSION
from app.tasks import PARSER_VERSION


@asynccontextmanager
async def lifespan(_app: FastAPI):
    if settings.secure_cookies and (settings.bootstrap_admin_password == "change-me-local" or "change-me@" in settings.database_url):
        raise RuntimeError("Production mode refuses default database or administrator credentials")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        admin = db.scalar(select(User).where(User.username == settings.bootstrap_admin_username))
        if admin is None:
            admin = User(username=settings.bootstrap_admin_username,
                         password_hash=hash_password(settings.bootstrap_admin_password), global_role="admin")
            db.add(admin)
            db.commit()
    if engine.dialect.name == "postgresql":
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE events ADD COLUMN IF NOT EXISTS session_id VARCHAR(255)"))
            connection.execute(text("ALTER TABLE events ADD COLUMN IF NOT EXISTS timestamp_confidence DOUBLE PRECISION NOT NULL DEFAULT 1.0"))
            connection.execute(text("ALTER TABLE events ADD COLUMN IF NOT EXISTS timestamp_assumptions JSON NOT NULL DEFAULT '[]'::json"))
            connection.execute(text("ALTER TABLE events ADD COLUMN IF NOT EXISTS year_source VARCHAR(64)"))
            connection.execute(text("ALTER TABLE events ADD COLUMN IF NOT EXISTS timezone_source VARCHAR(64)"))
            connection.execute(text("CREATE INDEX IF NOT EXISTS ix_events_session_id ON events (session_id)"))
            for statement in (
                "ALTER TABLE evidence_files ADD COLUMN IF NOT EXISTS job_id UUID",
                "ALTER TABLE evidence_files ADD COLUMN IF NOT EXISTS parsing_mode VARCHAR(32) NOT NULL DEFAULT 'strict'",
                "ALTER TABLE evidence_files ADD COLUMN IF NOT EXISTS total_lines INTEGER NOT NULL DEFAULT 0",
                "ALTER TABLE evidence_files ADD COLUMN IF NOT EXISTS processed_lines INTEGER NOT NULL DEFAULT 0",
                "ALTER TABLE evidence_files ADD COLUMN IF NOT EXISTS parsed_events INTEGER NOT NULL DEFAULT 0",
                "ALTER TABLE evidence_files ADD COLUMN IF NOT EXISTS malformed_lines INTEGER NOT NULL DEFAULT 0",
                "ALTER TABLE evidence_files ADD COLUMN IF NOT EXISTS progress_percent INTEGER NOT NULL DEFAULT 0",
                "ALTER TABLE evidence_files ADD COLUMN IF NOT EXISTS heartbeat_at TIMESTAMPTZ",
                "ALTER TABLE evidence_files ADD COLUMN IF NOT EXISTS retry_count INTEGER NOT NULL DEFAULT 0",
                "ALTER TABLE evidence_files ADD COLUMN IF NOT EXISTS completeness_ratio DOUBLE PRECISION NOT NULL DEFAULT 1.0",
                "ALTER TABLE evidence_files ADD COLUMN IF NOT EXISTS integrity_status VARCHAR(32)",
                "ALTER TABLE evidence_files ADD COLUMN IF NOT EXISTS integrity_verified_at TIMESTAMPTZ",
                "CREATE UNIQUE INDEX IF NOT EXISTS ix_evidence_files_job_id ON evidence_files (job_id)",
            ):
                connection.execute(text(statement))
    yield


app = FastAPI(title="TraceLens AI", version="0.1.0", lifespan=lifespan)
settings = get_settings()
rate_limiter = FixedWindowRateLimiter(settings.redis_url)
app.add_middleware(CORSMiddleware, allow_origins=[x.strip() for x in settings.cors_origins.split(",")],
                   allow_credentials=True, allow_methods=["GET", "POST", "PATCH"],
                   allow_headers=["Content-Type", "X-CSRF-Token"])

HTTP_REQUESTS = PromCounter("tracelens_http_requests_total", "HTTP requests", ["method", "route", "status"])
HTTP_LATENCY = Histogram("tracelens_http_request_duration_seconds", "HTTP request latency", ["method", "route"])
FINDING_QUEUE = Gauge("tracelens_findings_queue", "Findings by workflow status", ["status"])


@app.middleware("http")
async def observe_requests(request: Request, call_next):
    started = time.perf_counter()
    response_status = 500
    try:
        response = await call_next(request)
        response_status = response.status_code
        return response
    finally:
        route = getattr(request.scope.get("route"), "path", "unmatched")
        HTTP_REQUESTS.labels(request.method, route, str(response_status)).inc()
        HTTP_LATENCY.labels(request.method, route).observe(time.perf_counter() - started)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/ready")
def readiness(db: Session = Depends(get_db)) -> dict:
    db.execute(text("SELECT 1"))
    return {"status": "ready", "database": "ok", "parser_version": PARSER_VERSION,
            "risk_version": RISK_VERSION}


@app.get("/metrics", include_in_schema=False)
def metrics(db: Session = Depends(get_db)) -> Response:
    for state in ("new", "triaging", "escalated", "contained", "closed"):
        count = db.scalar(select(func.count()).select_from(Finding).where(Finding.workflow_status == state)) or 0
        FINDING_QUEUE.labels(state).set(count)
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.post("/auth/login", response_model=CurrentUserRead)
def login(payload: LoginRequest, response: Response, db: Session = Depends(get_db)) -> User:
    user = db.scalar(select(User).where(User.username == payload.username))
    if user is None or not user.is_active or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail={"code": "invalid_credentials", "message": "Invalid username or password"})
    token, csrf, _session = create_session(db, user, settings)
    db.add(AuditLog(action="user_login", actor=user.username, details={"user_id": str(user.user_id)}))
    db.commit()
    response.set_cookie(SESSION_COOKIE, token, httponly=True, secure=settings.secure_cookies,
                        samesite="strict", max_age=settings.session_ttl_hours * 3600, path="/")
    response.set_cookie(CSRF_COOKIE, csrf, httponly=False, secure=settings.secure_cookies,
                        samesite="strict", max_age=settings.session_ttl_hours * 3600, path="/")
    return user


@app.post("/auth/logout", status_code=204)
def logout(response: Response, request: Request, user: User = Depends(require_csrf),
           db: Session = Depends(get_db)) -> Response:
    session = request.state.session
    db.delete(session)
    db.add(AuditLog(action="user_logout", actor=user.username, details={"user_id": str(user.user_id)}))
    db.commit()
    response.delete_cookie(SESSION_COOKIE, path="/")
    response.delete_cookie(CSRF_COOKIE, path="/")
    return response


@app.get("/auth/me", response_model=CurrentUserRead)
def auth_me(user: User = Depends(get_current_user)) -> User:
    return user


def enforce_rate_limit(request: Request, endpoint: str, limit: int) -> None:
    client_ip = request.client.host if request.client else "unknown"
    try:
        rate_limiter.check(f"{endpoint}:{client_ip}", limit, settings.rate_limit_window_seconds)
    except RateLimitExceeded as exc:
        raise HTTPException(status_code=429, detail={"code": "rate_limit_exceeded", "message": "Too many requests"},
                            headers={"Retry-After": str(settings.rate_limit_window_seconds)}) from exc


def audit_upload_rejection(db: Session, case_id: uuid.UUID, reason: str, filename: str | None) -> None:
    db.add(AuditLog(case_id=case_id, action="evidence_upload_rejected",
                    details={"reason": reason, "filename_length": len(filename or "")}))
    db.commit()


def agent_audit_details(response: ChatResponse, metrics: dict, question: str) -> dict:
    return {"question_length": len(question), "claim_count": len(response.claims),
            "answer": response.answer,
            "claims": [{"claim_id": claim.claim_id, "text": claim.text, "status": claim.status,
                        "evidence_id": str(claim.evidence_id),
                        "supporting_evidence_ids": [str(item) for item in claim.supporting_evidence_ids],
                        "contradicting_evidence_ids": [str(item) for item in claim.contradicting_evidence_ids],
                        "confidence": claim.confidence, "limitations": claim.limitations}
                       for claim in response.claims],
            "evidence_ids": sorted({str(item) for claim in response.claims
                                    for item in (claim.supporting_evidence_ids or [claim.evidence_id])}),
            "tool_schema_version": TOOL_SCHEMA_VERSION, **metrics}


@app.post("/cases", response_model=CaseRead, status_code=status.HTTP_201_CREATED)
def create_case(payload: CaseCreate, user: User = Depends(require_csrf), db: Session = Depends(get_db)) -> Case:
    case = Case(**payload.model_dump())
    db.add(case)
    db.flush()
    db.add(CaseMembership(case_id=case.case_id, user_id=user.user_id, role="investigator"))
    db.add(AuditLog(case_id=case.case_id, action="case_created", actor=user.username,
                    details={"name": case.name, "user_id": str(user.user_id)}))
    db.commit()
    db.refresh(case)
    return case


@app.post("/cases/{case_id}/logs", response_model=EvidenceRead, status_code=status.HTTP_202_ACCEPTED)
async def upload_log(case_id: uuid.UUID, request: Request, file: UploadFile = File(...),
                     parsing_mode: str = Form("strict"),
                     user: User = Depends(require_case_permission("upload")),
                     _csrf: User = Depends(require_csrf), db: Session = Depends(get_db)) -> EvidenceFile:
    if parsing_mode not in {"strict", "quarantine"}:
        raise HTTPException(status_code=422, detail={"code": "invalid_parsing_mode", "message": "Parsing mode must be strict or quarantine"})
    enforce_rate_limit(request, "upload", settings.upload_rate_limit)
    try:
        safe_filename = validate_filename(file.filename)
        validate_mime_type(file.content_type)
    except UploadValidationError as exc:
        audit_upload_rejection(db, case_id, str(exc), file.filename)
        raise HTTPException(status_code=exc.status_code,
                            detail={"code": "invalid_upload", "message": str(exc)}) from exc
    evidence_id = uuid.uuid4()
    storage_dir = settings.evidence_storage_path
    storage_dir.mkdir(parents=True, exist_ok=True)
    path = safe_evidence_path(storage_dir, evidence_id)
    digest, size = hashlib.sha256(), 0
    decoder = codecs.getincrementaldecoder("utf-8")("strict")
    sample_parts: list[str] = []
    sample_chars = 0
    try:
        with path.open("xb") as output:
            while chunk := await file.read(1024 * 1024):
                new_size = validate_size(size, len(chunk), settings.max_upload_bytes)
                decoded = decoder.decode(chunk)
                if sample_chars < 128 * 1024:
                    remaining = 128 * 1024 - sample_chars
                    sample_parts.append(decoded[:remaining])
                    sample_chars += len(decoded[:remaining])
                digest.update(chunk)
                size = new_size
                output.write(chunk)
            tail = decoder.decode(b"", final=True)
            if sample_chars < 128 * 1024:
                sample_parts.append(tail[:128 * 1024 - sample_chars])
        detected_format = validate_text_and_detect("".join(sample_parts))
        os.chmod(path, 0o444)
    except (UploadValidationError, UnicodeDecodeError) as exc:
        path.unlink(missing_ok=True)
        validation = exc if isinstance(exc, UploadValidationError) else UploadValidationError("log file must be valid UTF-8")
        audit_upload_rejection(db, case_id, str(validation), safe_filename)
        raise HTTPException(status_code=validation.status_code,
                            detail={"code": "invalid_upload", "message": str(validation)}) from exc
    except Exception:
        path.unlink(missing_ok=True)
        raise
    job_id = uuid.uuid4()
    evidence = EvidenceFile(evidence_file_id=evidence_id, case_id=case_id, job_id=job_id, parsing_mode=parsing_mode,
                            original_filename=safe_filename, storage_path=str(path), detected_format=detected_format,
                            sha256=digest.hexdigest(), size_bytes=size, status="queued")
    db.add(evidence)
    db.flush()
    db.add(AuditLog(case_id=case_id, evidence_file_id=evidence_id, action="evidence_uploaded", actor=user.username,
                    details={"sha256": digest.hexdigest(), "size_bytes": size, "format": detected_format}))
    db.commit()
    parse_evidence_file.apply_async(args=[str(evidence_id)], task_id=str(job_id))
    return evidence


@app.get("/cases/{case_id}/logs", response_model=list[EvidenceRead])
def list_logs(case_id: uuid.UUID, _user: User = Depends(require_case_permission("read")),
              db: Session = Depends(get_db)) -> list[EvidenceFile]:
    return list(db.scalars(select(EvidenceFile).where(EvidenceFile.case_id == case_id)
                           .order_by(EvidenceFile.uploaded_at.desc(), EvidenceFile.evidence_file_id)))


@app.get("/cases/{case_id}/logs/{evidence_file_id}", response_model=EvidenceRead)
def get_log_status(case_id: uuid.UUID, evidence_file_id: uuid.UUID,
                   _user: User = Depends(require_case_permission("read")), db: Session = Depends(get_db)) -> EvidenceFile:
    evidence = db.scalar(select(EvidenceFile).where(EvidenceFile.case_id == case_id,
                                                    EvidenceFile.evidence_file_id == evidence_file_id))
    if evidence is None:
        raise HTTPException(status_code=404, detail={"code": "evidence_not_found", "message": "Evidence file not found"})
    return evidence


@app.get("/cases/{case_id}/jobs/{job_id}", response_model=EvidenceRead)
def get_job_status(case_id: uuid.UUID, job_id: uuid.UUID,
                   _user: User = Depends(require_case_permission("read")), db: Session = Depends(get_db)) -> EvidenceFile:
    evidence = db.scalar(select(EvidenceFile).where(EvidenceFile.case_id == case_id, EvidenceFile.job_id == job_id))
    if evidence is None:
        raise HTTPException(status_code=404, detail={"code": "job_not_found", "message": "Parsing job not found"})
    return evidence


@app.post("/cases/{case_id}/jobs/{job_id}/retry", response_model=EvidenceRead)
def retry_job(case_id: uuid.UUID, job_id: uuid.UUID,
              user: User = Depends(require_case_permission("upload")), _csrf: User = Depends(require_csrf),
              db: Session = Depends(get_db)) -> EvidenceFile:
    evidence = db.scalar(select(EvidenceFile).where(EvidenceFile.case_id == case_id, EvidenceFile.job_id == job_id))
    if evidence is None:
        raise HTTPException(status_code=404, detail={"code": "job_not_found", "message": "Parsing job not found"})
    if evidence.status not in {"failed", "stuck"}:
        raise HTTPException(status_code=409, detail={"code": "job_not_retryable", "message": "Only failed or stuck jobs can be retried"})
    evidence.status, evidence.error_message = "queued", None
    evidence.retry_count += 1
    evidence.job_id = uuid.uuid4()
    db.add(AuditLog(case_id=case_id, evidence_file_id=evidence.evidence_file_id,
                    action="evidence_parsing_retried", actor=user.username,
                    details={"retry_count": evidence.retry_count, "job_id": str(evidence.job_id)}))
    db.commit()
    parse_evidence_file.apply_async(args=[str(evidence.evidence_file_id)], task_id=str(evidence.job_id))
    return evidence


@app.post("/cases/{case_id}/logs/{evidence_file_id}/verify", response_model=IntegrityVerificationRead)
def verify_evidence_integrity(case_id: uuid.UUID, evidence_file_id: uuid.UUID,
                              user: User = Depends(require_case_permission("upload")), _csrf: User = Depends(require_csrf),
                              db: Session = Depends(get_db)) -> IntegrityVerificationRead:
    evidence = db.scalar(select(EvidenceFile).where(EvidenceFile.case_id == case_id,
                                                    EvidenceFile.evidence_file_id == evidence_file_id))
    if evidence is None:
        raise HTTPException(status_code=404, detail={"code": "evidence_not_found", "message": "Evidence file not found"})
    digest = hashlib.sha256()
    with open(evidence.storage_path, "rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    actual, verified_at = digest.hexdigest(), datetime.now(timezone.utc)
    integrity_status = "match" if actual == evidence.sha256 else "mismatch"
    evidence.integrity_status, evidence.integrity_verified_at = integrity_status, verified_at
    db.add(AuditLog(case_id=case_id, evidence_file_id=evidence_file_id, action="evidence_integrity_verified",
                    actor=user.username, details={"expected_sha256": evidence.sha256, "actual_sha256": actual,
                                                  "status": integrity_status}))
    db.commit()
    return IntegrityVerificationRead(evidence_file_id=evidence_file_id, expected_sha256=evidence.sha256,
                                     actual_sha256=actual, status=integrity_status, verified_at=verified_at)


@app.get("/cases/{case_id}/events", response_model=EventPage)
def list_events(
    case_id: uuid.UUID,
    page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200),
    source_type: str | None = None, username: str | None = None, source_ip: str | None = None,
    event_action: str | None = None, severity: str | None = None,
    _user: User = Depends(require_case_permission("read")), db: Session = Depends(get_db),
) -> EventPage:
    filters = [Event.case_id == case_id]
    for column, value in ((Event.source_type, source_type), (Event.username, username),
                          (Event.source_ip, source_ip), (Event.event_action, event_action)):
        if value is not None:
            filters.append(column == value)
    if severity is not None:
        filters.append(Event.severity == severity)
    total = db.scalar(select(func.count()).select_from(Event).where(*filters)) or 0
    statement = (select(Event).where(*filters).order_by(*timeline_order_by())
                 .offset((page - 1) * page_size).limit(page_size))
    return EventPage(items=list(db.scalars(statement)), page=page, page_size=page_size, total=total)


@app.get("/cases/{case_id}/events/{event_id}", response_model=EventContext)
def get_event_context(case_id: uuid.UUID, event_id: uuid.UUID, window: int = Query(5, ge=1, le=20),
                      _user: User = Depends(require_case_permission("read")), db: Session = Depends(get_db)) -> EventContext:
    target = db.scalar(select(Event).where(Event.case_id == case_id, Event.event_id == event_id))
    if target is None:
        raise HTTPException(status_code=404, detail={"code": "event_not_found", "message": "Event not found"})
    ordered = list(db.scalars(select(Event).where(Event.case_id == case_id).order_by(*timeline_order_by())))
    index = next(index for index, event in enumerate(ordered) if event.event_id == event_id)
    return EventContext(event=target, before=ordered[max(0, index - window):index], after=ordered[index + 1:index + 1 + window])


@app.get("/cases/{case_id}/timeline", response_model=TimelinePage)
def get_timeline(
    case_id: uuid.UUID, page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200),
    _user: User = Depends(require_case_permission("read")), db: Session = Depends(get_db),
) -> TimelinePage:
    total = db.scalar(select(func.count()).select_from(Event).where(Event.case_id == case_id)) or 0
    events = list(db.scalars(
        select(Event).where(Event.case_id == case_id)
        .order_by(*timeline_order_by())
        .offset((page - 1) * page_size).limit(page_size)
    ))
    event_ids = [event.event_id for event in events]
    correlations = [] if not event_ids else list(db.scalars(
        select(Correlation).where(Correlation.case_id == case_id).where(
            or_(Correlation.event_id.in_(event_ids), Correlation.related_event_id.in_(event_ids))
        ).order_by(Correlation.created_at, Correlation.correlation_id)
    ))
    by_event = {event_id: [] for event_id in event_ids}
    for correlation in correlations:
        if correlation.event_id in by_event:
            by_event[correlation.event_id].append(correlation)
        if correlation.related_event_id in by_event:
            by_event[correlation.related_event_id].append(correlation)
    return TimelinePage(
        items=[TimelineItem(event=EventRead.model_validate(event), correlations=by_event[event.event_id]) for event in events],
        page=page, page_size=page_size, total=total,
    )


@app.get("/cases/{case_id}/entities", response_model=list[EntityRead])
def get_entities(case_id: uuid.UUID, _user: User = Depends(require_case_permission("read")),
                 db: Session = Depends(get_db)) -> list[EntityRead]:
    entities: list[EntityRead] = []
    for entity_type, column in (("source_ip", Event.source_ip), ("username", Event.username), ("session", Event.session_id)):
        rows = db.execute(
            select(column, func.count(Event.event_id), func.min(Event.timestamp_normalized), func.max(Event.timestamp_normalized))
            .where(Event.case_id == case_id, column.is_not(None)).group_by(column).order_by(func.count(Event.event_id).desc(), column)
        )
        entities.extend(EntityRead(entity_type=entity_type, entity_value=value, event_count=count,
                                   first_seen=first_seen, last_seen=last_seen)
                        for value, count, first_seen, last_seen in rows)
    return entities


@app.get("/cases/{case_id}/findings", response_model=list[FindingRead])
def get_findings(case_id: uuid.UUID, _user: User = Depends(require_case_permission("read")),
                 db: Session = Depends(get_db)) -> list[Finding]:
    return list(db.scalars(select(Finding).where(Finding.case_id == case_id)
                           .order_by(Finding.risk_score.desc(), Finding.first_seen, Finding.finding_id)))


@app.patch("/cases/{case_id}/findings/{finding_id}", response_model=FindingRead)
def update_finding_workflow(case_id: uuid.UUID, finding_id: uuid.UUID, payload: FindingWorkflowUpdate,
                            user: User = Depends(require_case_permission("chat")),
                            _csrf: User = Depends(require_csrf), db: Session = Depends(get_db)) -> Finding:
    finding = db.scalar(select(Finding).where(Finding.case_id == case_id, Finding.finding_id == finding_id))
    if finding is None:
        raise HTTPException(status_code=404, detail={"code": "finding_not_found", "message": "Finding not found"})
    if payload.workflow_status == "closed" and payload.disposition is None:
        raise HTTPException(status_code=422, detail={"code": "disposition_required",
                                                     "message": "Closed findings require a disposition"})
    finding.workflow_status = payload.workflow_status
    finding.disposition = payload.disposition
    finding.assigned_to = payload.assigned_to or user.username
    finding.workflow_updated_at = datetime.now(timezone.utc)
    if payload.note:
        finding.analyst_notes = [*(finding.analyst_notes or []), {
            "author": user.username, "timestamp": finding.workflow_updated_at.isoformat(), "text": payload.note,
        }]
    db.add(AuditLog(case_id=case_id, action="finding_workflow_updated", actor=user.username,
                    details={"finding_id": str(finding_id), "status": finding.workflow_status,
                             "disposition": finding.disposition, "assigned_to": finding.assigned_to}))
    db.commit()
    db.refresh(finding)
    return finding


@app.post("/cases/{case_id}/analysis/rebuild")
def rebuild_analysis(case_id: uuid.UUID, user: User = Depends(require_case_permission("chat")),
                     _csrf: User = Depends(require_csrf), db: Session = Depends(get_db)) -> dict:
    correlation_count, finding_count = rebuild_case_analysis(db, case_id, settings)
    db.add(AuditLog(case_id=case_id, action="case_analysis_rebuilt", actor=user.username,
                    details={"correlation_count": correlation_count, "finding_count": finding_count,
                             "risk_version": RISK_VERSION}))
    db.commit()
    return {"status": "complete", "correlation_count": correlation_count,
            "finding_count": finding_count, "risk_version": RISK_VERSION}


@app.post("/cases/{case_id}/chat", response_model=ChatResponse)
def chat(case_id: uuid.UUID, payload: ChatRequest, request: Request,
         user: User = Depends(require_case_permission("chat")), _csrf: User = Depends(require_csrf),
         db: Session = Depends(get_db)) -> ChatResponse:
    enforce_rate_limit(request, "chat", settings.chat_rate_limit)
    try:
        response, metrics = LLMGateway(settings).chat(db, case_id, payload.question)
    except AgentRuntimeError as exc:
        db.add(AuditLog(case_id=case_id, action="agent_chat_failed", actor=user.username, model_version=settings.github_models_model,
                        prompt_version=PROMPT_VERSION, details={"error": str(exc)}))
        db.commit()
        raise HTTPException(status_code=503, detail={"code": "agent_unavailable", "message": str(exc)}) from exc
    db.add(AuditLog(case_id=case_id, action="agent_chat_completed", actor=user.username, model_version=settings.github_models_model,
                    prompt_version=PROMPT_VERSION,
                    details=agent_audit_details(response, metrics, payload.question)))
    db.commit()
    return response


def finding_recommendations(finding: Finding) -> list[tuple[str, str]]:
    common = [("Validasi", "Konfirmasi timestamp, akun, alamat IP, dan raw evidence sebelum melakukan containment."),
              ("Preservasi", "Pertahankan log asli beserta SHA-256 dan dokumentasikan setiap tindakan investigator.")]
    if finding.finding_type == "successful_login_after_failures":
        return [("Segera", "Isolasi atau batasi sesi aktif akun terkait dan paksa rotasi kredensial dari perangkat tepercaya."),
                ("Segera", "Periksa MFA, token API, SSH key, sesi browser, dan perubahan hak akses setelah login berhasil."),
                ("Investigasi", "Telusuri aktivitas pasca-login: sudo, pembuatan akun, persistence, akses file sensitif, dan koneksi keluar."),
                ("Containment", "Blokir atau rate-limit sumber setelah memastikan IP bukan shared IP, NAT, VPN resmi, atau scanner internal."),
                ("Pemulihan", "Aktifkan MFA tahan-phishing dan cabut seluruh sesi/token jika login tidak dapat divalidasi sebagai sah.")] + common
    if finding.finding_type == "brute_force":
        return [("Segera", "Terapkan rate limiting, exponential backoff, atau temporary lockout pada autentikasi."),
                ("Pencegahan", "Wajibkan MFA dan nonaktifkan login password untuk akun administratif bila memungkinkan."),
                ("Monitoring", "Buat alert untuk kegagalan berulang lintas akun/IP dan keberhasilan login setelah rangkaian kegagalan."),
                ("Hardening", "Batasi SSH/admin interface melalui allowlist, VPN, bastion host, atau segmentasi jaringan."),
                ("Validasi", "Periksa apakah sumber merupakan shared IP, NAT, VPN resmi, vulnerability scanner, atau pengujian resmi sebelum memblokirnya.")] + common
    return [("Tinjau", "Validasi finding terhadap raw evidence dan konteks operasional sistem."),
            ("Mitigasi", "Kurangi exposure terkait dan tingkatkan monitoring terhadap entity yang teridentifikasi.")] + common


def build_markdown_report(case_id: uuid.UUID, findings: list[Finding], evidence_files: list[EvidenceFile] | None = None,
                          *, case_name: str | None = None, events: list[Event] | None = None) -> str:
    events = events or []
    highest = max((item.risk_score for item in findings), default=0.0)
    risk_level = ("critical" if highest >= .85 else "high" if highest >= .7 else
                  "medium" if highest >= .4 else "low")
    lines = ["# TraceLens AI — Laporan Investigasi", "",
             f"**Case:** {case_name or case_id}  ", f"**Case ID:** `{case_id}`  ",
             f"**Dibuat:** {datetime.now(timezone.utc).isoformat()}  ",
             "", "> **Catatan penting:** Skor risiko bersifat heuristik dan belum dikalibrasi sebagai probabilitas kompromi.",
             "", "## 1. Ringkasan Eksekutif", "",
             f"Analisis memproses **{len(events)} event**, menghasilkan **{len(findings)} temuan**, "
             f"dan mengidentifikasi tingkat risiko heuristik tertinggi **{risk_level.upper()} ({highest*100:.0f}/100)**.", "",
             "| Metrik | Nilai |", "|---|---:|", f"| Event terstruktur | {len(events)} |",
             f"| Temuan rule-based | {len(findings)} |", f"| Berkas evidence | {len(evidence_files or [])} |",
             f"| Risk heuristik tertinggi | {highest*100:.0f}/100 ({risk_level}) |",
             "", "## 2. Temuan dan Rekomendasi"]
    if not findings:
        lines.extend(["", "Belum ada temuan rule-based. Kondisi ini tidak membuktikan bahwa sistem bebas insiden; tinjau kelengkapan evidence dan telemetry tambahan."])
    for index, finding in enumerate(findings, 1):
        breakdown = finding.risk_breakdown or {}
        lines.extend(["", f"### 2.{index} {finding.title}", "", finding.description, "",
                      "| Atribut | Nilai |", "|---|---|",
                      f"| Tingkat risiko | **{str(breakdown.get('risk_level','unknown')).upper()}** |",
                      f"| Skor heuristik | **{finding.risk_score*100:.0f}/100** |",
                      f"| Confidence evidence | **{finding.confidence_score*100:.0f}/100** |",
                      f"| MITRE ATT&CK | {finding.mitre_technique or 'Belum dipetakan'} / {finding.mitre_tactic or '—'} |",
                      f"| Entity | `{finding.entity_type} = {finding.entity_value}` |",
                      f"| Rentang waktu | {finding.first_seen.isoformat()} — {finding.last_seen.isoformat()} |",
                      f"| Jumlah evidence | {len(finding.evidence_ids)} |", "",
                      "#### Rekomendasi tindakan", ""])
        for priority, recommendation in finding_recommendations(finding):
            lines.append(f"- **{priority}:** {recommendation}")
        lines.extend(["", "#### Pertimbangan false positive", ""] +
                     [f"- {item}" for item in (finding.false_positive_considerations or [])] +
                     ["", "#### Investigasi lanjutan", ""] +
                     [f"- {item}" for item in (finding.recommended_queries or [])])
        lines.extend(["", "<details>", "<summary>Evidence IDs dan breakdown teknis</summary>", "",
                      "**Evidence IDs**", ""] + [f"- `{item}`" for item in finding.evidence_ids] +
                     ["", "```json", json.dumps(finding.risk_breakdown, indent=2), "```", "", "</details>"])
    lines.extend(["", "## 3. Rundown Timeline", ""])
    if not events:
        lines.append("Rundown event tidak tersedia pada export ini.")
    else:
        lines.extend(["| Waktu | Severity | Aksi / outcome | Entity | Evidence |", "|---|---|---|---|---|"])
        for event in events[:100]:
            entity = event.source_ip or event.username or event.host or event.source_name or "—"
            timestamp = event.timestamp_normalized.isoformat() if event.timestamp_normalized else "—"
            lines.append(f"| {timestamp} | {event.severity} | {event.event_action} / {event.event_outcome or '—'} | {entity} | `{event.event_id}` L{event.raw_line_number} |")
        if len(events) > 100:
            lines.extend(["", f"> Rundown dibatasi 100 dari {len(events)} event. Gunakan halaman Timeline untuk meninjau keseluruhan event."])
    lines.extend(["", "## 4. Evidence Appendix", ""])
    for evidence in evidence_files or []:
        lines.extend([f"### {evidence.original_filename}",
                      f"- Evidence file ID: {evidence.evidence_file_id}",
                      f"- SHA-256: `{evidence.sha256}`", f"- Integrity: {evidence.integrity_status or 'not_verified'}",
                      f"- Parser mode/status: {evidence.parsing_mode} / {evidence.status}",
                      f"- Completeness: {evidence.completeness_ratio:.5f}", ""])
    lines.extend(["## 5. Metodologi dan Version Appendix", "",
                  "Parsing, timeline, korelasi, finding, dan risk scoring dilakukan secara deterministik. LLM hanya digunakan untuk interpretasi berbasis tool dan claim yang lolos verification gate.", "",
                  f"- Parser: {PARSER_VERSION}",
                  f"- Timeline sorting: {TIMELINE_SORT_VERSION}", f"- Risk model: {RISK_VERSION}",
                  f"- Risk thresholds: {RISK_THRESHOLD_VERSION}", f"- Prompt: {PROMPT_VERSION}",
                  f"- Tool schema: {TOOL_SCHEMA_VERSION}", f"- Model: {settings.github_models_model}"])
    lines.extend(["", "## 6. Batasan", "",
                  "- Citation valid menunjukkan evidence tersedia, tetapi interpretasi tetap harus ditinjau investigator.",
                  "- Tidak adanya finding bukan bukti bahwa insiden tidak terjadi.",
                  "- Rekomendasi harus disesuaikan dengan dampak bisnis, arsitektur, dan prosedur respons organisasi."])
    return "\n".join(lines)


def build_pdf_report(case: Case, findings: list[Finding], evidence_files: list[EvidenceFile],
                     events: list[Event]) -> bytes:
    buffer = BytesIO()
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="ReportTitle", parent=styles["Title"], alignment=TA_CENTER,
                              textColor=colors.HexColor("#17365D"), spaceAfter=8))
    styles.add(ParagraphStyle(name="SmallReport", parent=styles["BodyText"], fontSize=8, leading=10))
    document = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=16*mm, leftMargin=16*mm,
                                 topMargin=16*mm, bottomMargin=16*mm,
                                 title=f"Laporan Investigasi {case.name}")
    story = [Paragraph("TraceLens AI — Laporan Investigasi", styles["ReportTitle"]),
             Paragraph(f"Case: {case.name}", styles["Heading2"]),
             Paragraph(f"Case ID: {case.case_id}", styles["SmallReport"]), Spacer(1, 4*mm)]
    highest = max((item.risk_score for item in findings), default=0.0)
    summary = [["Event", "Temuan", "Evidence file", "Risk heuristik tertinggi"],
               [str(len(events)), str(len(findings)), str(len(evidence_files)), f"{highest*100:.0f}/100"]]
    table = Table(summary, colWidths=[38*mm]*4)
    table.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.HexColor("#17365D")),
                               ("TEXTCOLOR",(0,0),(-1,0),colors.white),("GRID",(0,0),(-1,-1),.4,colors.grey),
                               ("ALIGN",(0,0),(-1,-1),"CENTER"),("FONTNAME",(0,0),(-1,0),"Helvetica-Bold"),
                               ("PADDING",(0,0),(-1,-1),6)]))
    story.extend([table, Spacer(1, 5*mm), Paragraph("Rundown Timeline", styles["Heading2"])])
    if not events:
        story.append(Paragraph("Belum ada event terstruktur pada case ini.", styles["BodyText"]))
    else:
        rows = [["Waktu", "Severity", "Aksi / outcome", "Entity", "Evidence"]]
        for event in events[:100]:
            entity = event.source_ip or event.username or event.host or event.source_name
            rows.append([event.timestamp_normalized.isoformat() if event.timestamp_normalized else "—",
                         event.severity, f"{event.event_action} / {event.event_outcome or '—'}", entity or "—",
                         f"{str(event.event_id)[:8]}… L{event.raw_line_number}"])
        timeline = Table(rows, repeatRows=1, colWidths=[36*mm,20*mm,45*mm,34*mm,30*mm])
        timeline.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.HexColor("#D9EAF7")),
                                      ("GRID",(0,0),(-1,-1),.25,colors.HexColor("#AAB7C4")),
                                      ("VALIGN",(0,0),(-1,-1),"TOP"),("FONTSIZE",(0,0),(-1,-1),7),
                                      ("FONTNAME",(0,0),(-1,0),"Helvetica-Bold"),("PADDING",(0,0),(-1,-1),3)]))
        story.append(timeline)
        if len(events)>100:
            story.append(Paragraph(f"Rundown dibatasi 100 dari {len(events)} event.", styles["SmallReport"]))
    story.extend([PageBreak(), Paragraph("Temuan Rule-based", styles["Heading2"])])
    if not findings:
        story.append(Paragraph("Belum ada temuan rule-based.", styles["BodyText"]))
    for index, finding in enumerate(findings,1):
        story.extend([Paragraph(f"{index}. {html.escape(finding.title)}", styles["Heading3"]),
                      Paragraph(html.escape(finding.description), styles["BodyText"]),
                      Paragraph(f"Risk heuristik: {finding.risk_score*100:.0f}/100 · Entity: {html.escape(finding.entity_type)} = {html.escape(finding.entity_value)}", styles["SmallReport"]),
                      Paragraph("Evidence IDs: " + ", ".join(finding.evidence_ids), styles["SmallReport"]), Spacer(1,3*mm)])
        story.append(Paragraph("Rekomendasi tindakan", styles["Heading4"]))
        for priority, recommendation in finding_recommendations(finding):
            story.append(Paragraph(f"<b>{html.escape(priority)}:</b> {html.escape(recommendation)}", styles["BodyText"]))
        story.append(Spacer(1, 3*mm))
    story.append(Paragraph("Evidence Manifest", styles["Heading2"]))
    for evidence in evidence_files:
        story.extend([Paragraph(evidence.original_filename, styles["Heading3"]),
                      Paragraph(f"ID: {evidence.evidence_file_id}<br/>SHA-256: {evidence.sha256}<br/>Integrity: {evidence.integrity_status or 'not_verified'}<br/>Status: {evidence.status} · Completeness: {evidence.completeness_ratio:.5f}", styles["SmallReport"])])
    story.extend([Spacer(1,5*mm), Paragraph("Version Appendix", styles["Heading2"]),
                  Paragraph(f"Parser {PARSER_VERSION} · Timeline {TIMELINE_SORT_VERSION} · Risk {RISK_VERSION} · Prompt {PROMPT_VERSION} · Tools {TOOL_SCHEMA_VERSION} · Model {settings.github_models_model}", styles["SmallReport"]),
                  Paragraph("Catatan: risk score bersifat heuristik dan bukan probabilitas kompromi. Interpretasi AI wajib diverifikasi investigator.", styles["SmallReport"])])
    document.build(story)
    return buffer.getvalue()


def build_formal_pdf_report(case: Case, findings: list[Finding], evidence_files: list[EvidenceFile],
                            events: list[Event]) -> bytes:
    """Build a portrait A4 report whose table cells always wrap within their columns."""
    buffer = BytesIO()
    styles = getSampleStyleSheet()
    # Monochrome palette: deliberately safe for printing and photocopying.
    navy = colors.HexColor("#111111")
    blue = colors.HexColor("#3A3A3A")
    pale = colors.HexColor("#ECECEC")
    border = colors.HexColor("#A6A6A6")
    styles.add(ParagraphStyle(name="FormalTitle", parent=styles["Title"], alignment=TA_CENTER,
                              fontName="Helvetica-Bold", fontSize=18, leading=22,
                              textColor=navy, spaceAfter=3*mm))
    styles.add(ParagraphStyle(name="FormalSubtitle", parent=styles["BodyText"], alignment=TA_CENTER,
                              fontSize=10, leading=13, textColor=colors.HexColor("#404040"), spaceAfter=6*mm))
    styles.add(ParagraphStyle(name="FormalSection", parent=styles["Heading2"], fontName="Helvetica-Bold",
                              fontSize=12, leading=15, textColor=navy, spaceBefore=5*mm,
                              spaceAfter=2.5*mm, keepWithNext=True))
    styles.add(ParagraphStyle(name="FormalSubsection", parent=styles["Heading3"], fontName="Helvetica-Bold",
                              fontSize=10, leading=13, textColor=blue, spaceBefore=3*mm,
                              spaceAfter=1.5*mm, keepWithNext=True))
    styles.add(ParagraphStyle(name="FormalBody", parent=styles["BodyText"], fontSize=8.7,
                              leading=12, spaceAfter=2*mm))
    styles.add(ParagraphStyle(name="FormalSmall", parent=styles["BodyText"], fontSize=7.4,
                              leading=9.5, textColor=colors.HexColor("#404040")))
    # CJK wrapping deliberately allows breaks inside UUIDs, paths, hashes, and URLs.
    styles.add(ParagraphStyle(name="FormalCell", parent=styles["BodyText"], fontSize=6.5,
                              leading=8.1, wordWrap="CJK", splitLongWords=True))
    styles.add(ParagraphStyle(name="FormalCellCenter", parent=styles["FormalCell"], alignment=TA_CENTER))
    styles.add(ParagraphStyle(name="FormalHeaderCell", parent=styles["FormalCell"],
                              fontName="Helvetica-Bold", fontSize=6.7, leading=8.2,
                              textColor=colors.white, alignment=TA_CENTER))
    document = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=16*mm, leftMargin=16*mm,
                                 topMargin=21*mm, bottomMargin=18*mm,
                                 title=f"Laporan Investigasi {case.name}")

    def cell(value, style="FormalCell"):
        shown = "—" if value in (None, "") else str(value)
        return Paragraph(html.escape(shown), styles[style])

    def timestamp(value):
        return value.strftime("%Y-%m-%d %H:%M:%S %z") if value else "—"

    def padded_table_style(extra=None):
        commands = [("GRID", (0, 0), (-1, -1), .3, border),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 4),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]
        return TableStyle(commands + (extra or []))

    def bar_chart(title: str, counts: Counter, width=84*mm, height=43*mm):
        drawing = Drawing(width, height)
        drawing.add(Rect(0, 0, width, height, fillColor=colors.white, strokeColor=border, strokeWidth=.5))
        drawing.add(String(5*mm, height-6*mm, title, fontName="Helvetica-Bold", fontSize=8,
                           fillColor=colors.black))
        items = sorted(counts.items(), key=lambda item: (-item[1], str(item[0])))[:5]
        if not items:
            drawing.add(String(5*mm, height-18*mm, "Tidak ada data", fontName="Helvetica",
                               fontSize=7, fillColor=colors.HexColor("#555555")))
            return drawing
        maximum = max(value for _, value in items) or 1
        label_x, bar_x, bar_max = 5*mm, 35*mm, width-48*mm
        row_height = 6.1*mm
        shades = ["#222222", "#444444", "#666666", "#888888", "#AAAAAA"]
        for index, (label, value) in enumerate(items):
            y = height-14*mm-index*row_height
            label_text = str(label or "unknown")
            if len(label_text) > 17:
                label_text = label_text[:16] + "..."
            drawing.add(String(label_x, y+1.2*mm, label_text, fontName="Helvetica", fontSize=6.5,
                               fillColor=colors.black))
            drawing.add(Rect(bar_x, y, bar_max, 3.5*mm, fillColor=colors.HexColor("#F2F2F2"),
                             strokeColor=border, strokeWidth=.25))
            drawing.add(Rect(bar_x, y, max(1.2*mm, bar_max*value/maximum), 3.5*mm,
                             fillColor=colors.HexColor(shades[index]), strokeColor=None))
            drawing.add(String(width-11*mm, y+1.1*mm, str(value), fontName="Helvetica-Bold",
                               fontSize=6.5, fillColor=colors.black))
        return drawing

    def header_footer(canvas, doc):
        canvas.saveState()
        width, height = A4
        canvas.setStrokeColor(border)
        canvas.setLineWidth(.4)
        canvas.line(16*mm, height-14*mm, width-16*mm, height-14*mm)
        canvas.line(16*mm, 12*mm, width-16*mm, 12*mm)
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(colors.HexColor("#5A6573"))
        canvas.drawString(16*mm, height-11*mm, "TRACELENS AI - LAPORAN INVESTIGASI")
        canvas.drawRightString(width-16*mm, height-11*mm, str(case.case_id))
        canvas.drawString(16*mm, 8.5*mm, "Dokumen analisis - verifikasi investigator diperlukan")
        canvas.drawRightString(width-16*mm, 8.5*mm, f"Halaman {doc.page}")
        canvas.restoreState()

    created_at = datetime.now(timezone.utc)
    story = [Paragraph("TraceLens AI", styles["FormalTitle"]),
             Paragraph("LAPORAN INVESTIGASI LOG", styles["FormalSubtitle"])]
    metadata = [[cell("Nama kasus", "FormalHeaderCell"), cell(case.name),
                 cell("Tanggal laporan", "FormalHeaderCell"), cell(created_at.strftime("%d-%m-%Y %H:%M UTC"))],
                [cell("Case ID", "FormalHeaderCell"), cell(case.case_id),
                 cell("Status dokumen", "FormalHeaderCell"), cell("Analisis otomatis - perlu verifikasi")]]
    metadata_table = Table(metadata, colWidths=[28*mm, 61*mm, 29*mm, 60*mm])
    metadata_table.setStyle(padded_table_style([
        ("BACKGROUND", (0,0), (0,-1), navy), ("BACKGROUND", (2,0), (2,-1), navy),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE")]))
    story.extend([metadata_table, Paragraph("1. Ringkasan Eksekutif", styles["FormalSection"])])

    highest = max((item.risk_score for item in findings), default=0.0)
    risk_level = ("KRITIS" if highest >= .85 else "TINGGI" if highest >= .7 else
                  "SEDANG" if highest >= .4 else "RENDAH")
    summary = [[cell("Event terstruktur", "FormalHeaderCell"), cell("Temuan", "FormalHeaderCell"),
                cell("Berkas evidence", "FormalHeaderCell"), cell("Risiko heuristik", "FormalHeaderCell")],
               [cell(len(events), "FormalCellCenter"), cell(len(findings), "FormalCellCenter"),
                cell(len(evidence_files), "FormalCellCenter"),
                cell(f"{highest*100:.0f}/100 - {risk_level}", "FormalCellCenter")]]
    summary_table = Table(summary, colWidths=[44.5*mm]*4)
    summary_table.setStyle(padded_table_style([
        ("BACKGROUND",(0,0),(-1,0),navy), ("BACKGROUND",(0,1),(-1,1),pale),
        ("VALIGN",(0,0),(-1,-1),"MIDDLE")]))
    severity_counts = Counter(str(event.severity or "unknown").lower() for event in events)
    outcome_counts = Counter(str(event.event_outcome or "tanpa outcome").lower() for event in events)
    charts = Table([[bar_chart("Distribusi Severity", severity_counts),
                     bar_chart("Distribusi Outcome", outcome_counts)]],
                   colWidths=[89*mm, 89*mm])
    charts.setStyle(TableStyle([("VALIGN",(0,0),(-1,-1),"TOP"),
                                ("LEFTPADDING",(0,0),(-1,-1),0), ("RIGHTPADDING",(0,0),(-1,-1),0),
                                ("TOPPADDING",(0,0),(-1,-1),2*mm), ("BOTTOMPADDING",(0,0),(-1,-1),1*mm)]))
    story.extend([summary_table, charts,
                  Paragraph("Grafik menampilkan maksimal lima kategori terbesar. Skor risiko bersifat heuristik dan bukan probabilitas kompromi. Tidak adanya temuan rule-based tidak membuktikan bahwa sistem bebas insiden.", styles["FormalSmall"]),
                  Paragraph("2. Temuan dan Rekomendasi", styles["FormalSection"])])

    if not findings:
        story.append(Paragraph("Belum ada temuan rule-based. Tinjau kelengkapan evidence, cakupan telemetry, dan event dengan parser confidence rendah.", styles["FormalBody"]))
    for index, finding in enumerate(findings, 1):
        story.extend([Paragraph(f"2.{index} {html.escape(finding.title)}", styles["FormalSubsection"]),
                      Paragraph(html.escape(finding.description), styles["FormalBody"])])
        details = Table([
            [cell("Risk / confidence", "FormalHeaderCell"), cell(f"{finding.risk_score*100:.0f}/100 / {finding.confidence_score*100:.0f}/100"),
             cell("MITRE / entity", "FormalHeaderCell"), cell(f"{finding.mitre_technique or 'N/A'} {finding.mitre_tactic or ''} | {finding.entity_type} = {finding.entity_value}")],
            [cell("Periode", "FormalHeaderCell"), cell(f"{timestamp(finding.first_seen)} s.d. {timestamp(finding.last_seen)}"),
             cell("Evidence", "FormalHeaderCell"), cell(f"{len(finding.evidence_ids)} event")]],
            colWidths=[20*mm, 46*mm, 20*mm, 92*mm])
        details.setStyle(padded_table_style([
            ("BACKGROUND",(0,0),(0,-1),blue), ("BACKGROUND",(2,0),(2,-1),blue)]))
        story.extend([details, Paragraph("Rekomendasi tindakan", styles["FormalSubsection"])])
        for priority, recommendation in finding_recommendations(finding):
            story.append(Paragraph(f"- <b>{html.escape(priority)}:</b> {html.escape(recommendation)}", styles["FormalBody"]))
        if finding.false_positive_considerations:
            story.append(Paragraph("Pertimbangan false positive", styles["FormalSubsection"]))
            for item in finding.false_positive_considerations:
                story.append(Paragraph(f"- {html.escape(item)}", styles["FormalBody"]))
        if finding.recommended_queries:
            story.append(Paragraph("Investigasi lanjutan", styles["FormalSubsection"]))
            for item in finding.recommended_queries:
                story.append(Paragraph(f"- {html.escape(item)}", styles["FormalBody"]))

    story.extend([PageBreak(), Paragraph("3. Rundown Timeline", styles["FormalSection"])])
    if not events:
        story.append(Paragraph("Belum ada event terstruktur pada kasus ini.", styles["FormalBody"]))
    else:
        rows = [[cell("Waktu", "FormalHeaderCell"), cell("Severity", "FormalHeaderCell"),
                 cell("Aksi / outcome", "FormalHeaderCell"), cell("Entity", "FormalHeaderCell"),
                 cell("Evidence", "FormalHeaderCell")]]
        for event in events[:100]:
            entity = event.source_ip or event.username or event.host or event.source_name
            rows.append([cell(timestamp(event.timestamp_normalized)), cell(event.severity, "FormalCellCenter"),
                         cell(f"{event.event_action} / {event.event_outcome or '—'}"), cell(entity),
                         cell(f"{str(event.event_id)[:8]}... - L{event.raw_line_number}")])
        timeline = Table(rows, repeatRows=1, colWidths=[34*mm,18*mm,38*mm,58*mm,30*mm], splitByRow=True)
        timeline.setStyle(padded_table_style([
            ("BACKGROUND",(0,0),(-1,0),navy),
            ("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white, colors.HexColor("#F5F8FA")])]))
        story.append(timeline)
        if len(events) > 100:
            story.append(Paragraph(f"Rundown dibatasi 100 dari {len(events)} event.", styles["FormalSmall"]))

    story.extend([PageBreak(), Paragraph("4. Evidence Manifest", styles["FormalSection"])])
    if evidence_files:
        manifest = [[cell("Nama file", "FormalHeaderCell"), cell("SHA-256", "FormalHeaderCell"),
                     cell("Status", "FormalHeaderCell"), cell("Completeness", "FormalHeaderCell")]]
        for evidence in evidence_files:
            manifest.append([cell(evidence.original_filename), cell(evidence.sha256),
                             cell(f"{evidence.integrity_status or 'not verified'} / {evidence.status}"),
                             cell(f"{evidence.completeness_ratio:.2%}", "FormalCellCenter")])
        manifest_table = Table(manifest, repeatRows=1,
                               colWidths=[43*mm,75*mm,42*mm,18*mm], splitByRow=True)
        manifest_table.setStyle(padded_table_style([
            ("BACKGROUND",(0,0),(-1,0),navy),
            ("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white,pale])]))
        story.append(manifest_table)
    else:
        story.append(Paragraph("Tidak ada berkas evidence pada kasus ini.", styles["FormalBody"]))
    story.extend([
        Paragraph("5. Metodologi dan Versi", styles["FormalSection"]),
        Paragraph("Parsing, timeline, korelasi, finding, dan risk scoring dilakukan secara deterministik. LLM digunakan untuk interpretasi berbasis tool; claim tetap melewati verification gate.", styles["FormalBody"]),
        Paragraph(f"Parser: {PARSER_VERSION}<br/>Timeline: {TIMELINE_SORT_VERSION}<br/>Risk model: {RISK_VERSION}<br/>Prompt: {PROMPT_VERSION}<br/>Tool schema: {TOOL_SCHEMA_VERSION}<br/>Model: {html.escape(settings.github_models_model)}", styles["FormalSmall"]),
        Paragraph("6. Batasan", styles["FormalSection"]),
        Paragraph("- Citation valid menunjukkan evidence tersedia, tetapi interpretasi tetap harus ditinjau investigator.<br/>- Tidak adanya finding bukan bukti bahwa insiden tidak terjadi.<br/>- Rekomendasi harus disesuaikan dengan dampak bisnis, arsitektur, dan prosedur respons organisasi.", styles["FormalBody"])])
    document.build(story, onFirstPage=header_footer, onLaterPages=header_footer)
    return buffer.getvalue()


@app.post("/cases/{case_id}/exports", response_model=ReportExportResponse)
def export_report(case_id: uuid.UUID, payload: ReportExportRequest,
                  user: User = Depends(require_case_permission("export")), _csrf: User = Depends(require_csrf),
                  db: Session = Depends(get_db)) -> ReportExportResponse:
    evidence_files = list(db.scalars(select(EvidenceFile).where(EvidenceFile.case_id == case_id)))
    for evidence in evidence_files:
        digest = hashlib.sha256()
        with open(evidence.storage_path, "rb") as handle:
            while chunk := handle.read(1024 * 1024):
                digest.update(chunk)
        actual = digest.hexdigest()
        evidence.integrity_status = "match" if actual == evidence.sha256 else "mismatch"
        evidence.integrity_verified_at = datetime.now(timezone.utc)
        db.add(AuditLog(case_id=case_id, evidence_file_id=evidence.evidence_file_id,
                        action="evidence_integrity_verified_before_export", actor=user.username,
                        details={"expected_sha256": evidence.sha256, "actual_sha256": actual,
                                 "status": evidence.integrity_status}))
    if any(item.integrity_status == "mismatch" for item in evidence_files):
        raise HTTPException(status_code=409, detail={"code": "evidence_integrity_failed", "message": "Report blocked because evidence integrity verification failed"})
    if any(item.status == "parsed_with_warnings" for item in evidence_files) and not payload.acknowledge_warnings:
        raise HTTPException(status_code=409, detail={"code": "parsing_warnings_unacknowledged", "message": "Acknowledge parsing warnings before exporting the report"})
    case = db.scalar(select(Case).where(Case.case_id == case_id))
    if case is None:
        raise HTTPException(status_code=404, detail="case not found")
    findings = list(db.scalars(select(Finding).where(Finding.case_id == case_id)
                               .order_by(Finding.risk_score.desc(), Finding.first_seen, Finding.finding_id)))
    events = list(db.scalars(select(Event).where(Event.case_id == case_id).order_by(*timeline_order_by())))
    export_id = uuid.uuid4()
    content = (build_markdown_report(case_id, findings, evidence_files, case_name=case.name, events=events) if payload.format == "markdown"
               else base64.b64encode(build_formal_pdf_report(case, findings, evidence_files, events)).decode("ascii"))
    evidence_ids = sorted({str(evidence_id) for finding in findings for evidence_id in finding.evidence_ids})
    db.add(AuditLog(case_id=case_id, action="report_export_generated", actor=user.username,
                    details={"export_id": str(export_id), "format": payload.format,
                             "finding_count": len(findings), "event_count": len(events),
                             "evidence_ids": evidence_ids}))
    db.commit()
    return ReportExportResponse(export_id=export_id, format=payload.format, content=content)
