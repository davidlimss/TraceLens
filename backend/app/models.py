import uuid
from datetime import datetime, timezone

from sqlalchemy import DDL, DateTime, Float, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint, event
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Case(Base):
    __tablename__ = "cases"
    case_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    evidence_files: Mapped[list["EvidenceFile"]] = relationship(back_populates="case")


class User(Base):
    __tablename__ = "users"
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    username: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(512))
    global_role: Mapped[str] = mapped_column(String(32), default="user")
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class UserSession(Base):
    __tablename__ = "user_sessions"
    session_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.user_id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    csrf_hash: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class CaseMembership(Base):
    __tablename__ = "case_memberships"
    membership_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cases.case_id", ondelete="CASCADE"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.user_id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (UniqueConstraint("case_id", "user_id", name="uq_case_membership"),)


class EvidenceFile(Base):
    __tablename__ = "evidence_files"
    evidence_file_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cases.case_id", ondelete="RESTRICT"), index=True)
    original_filename: Mapped[str] = mapped_column(String(512))
    storage_path: Mapped[str] = mapped_column(String(1024), unique=True)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    size_bytes: Mapped[int] = mapped_column(Integer)
    detected_format: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32), default="uploaded")
    error_message: Mapped[str | None] = mapped_column(Text)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    parsed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    job_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), unique=True, index=True)
    parsing_mode: Mapped[str] = mapped_column(String(32), default="strict")
    total_lines: Mapped[int] = mapped_column(Integer, default=0)
    processed_lines: Mapped[int] = mapped_column(Integer, default=0)
    parsed_events: Mapped[int] = mapped_column(Integer, default=0)
    malformed_lines: Mapped[int] = mapped_column(Integer, default=0)
    progress_percent: Mapped[int] = mapped_column(Integer, default=0)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    completeness_ratio: Mapped[float] = mapped_column(Float, default=1.0)
    integrity_status: Mapped[str | None] = mapped_column(String(32))
    integrity_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    case: Mapped[Case] = relationship(back_populates="evidence_files")


class Event(Base):
    __tablename__ = "events"
    event_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cases.case_id", ondelete="RESTRICT"), index=True)
    evidence_file_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("evidence_files.evidence_file_id", ondelete="RESTRICT"), index=True)
    timestamp_original: Mapped[str | None] = mapped_column(String(255))
    timestamp_normalized: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    timezone: Mapped[str | None] = mapped_column(String(64))
    source_type: Mapped[str] = mapped_column(String(64), index=True)
    source_name: Mapped[str] = mapped_column(String(255))
    host: Mapped[str | None] = mapped_column(String(255))
    event_category: Mapped[str] = mapped_column(String(64), index=True)
    event_action: Mapped[str] = mapped_column(String(128), index=True)
    event_outcome: Mapped[str | None] = mapped_column(String(32))
    severity: Mapped[str] = mapped_column(String(32), default="info")
    username: Mapped[str | None] = mapped_column(String(255), index=True)
    source_ip: Mapped[str | None] = mapped_column(String(45), index=True)
    destination_ip: Mapped[str | None] = mapped_column(String(45))
    process_name: Mapped[str | None] = mapped_column(String(255))
    file_name: Mapped[str | None] = mapped_column(String(512))
    raw_log: Mapped[str] = mapped_column(Text)
    raw_line_number: Mapped[int] = mapped_column(Integer)
    parser_name: Mapped[str] = mapped_column(String(128))
    parser_confidence: Mapped[float] = mapped_column(Float)
    tags: Mapped[list] = mapped_column(JSON, default=list)
    session_id: Mapped[str | None] = mapped_column(String(255), index=True)
    timestamp_confidence: Mapped[float] = mapped_column(Float, default=1.0)
    timestamp_assumptions: Mapped[list] = mapped_column(JSON, default=list)
    year_source: Mapped[str | None] = mapped_column(String(64))
    timezone_source: Mapped[str | None] = mapped_column(String(64))
    event_code: Mapped[str | None] = mapped_column(String(128), index=True)
    command_line: Mapped[str | None] = mapped_column(Text)
    parent_process_name: Mapped[str | None] = mapped_column(String(512))
    source_port: Mapped[int | None] = mapped_column(Integer)
    destination_port: Mapped[int | None] = mapped_column(Integer)
    protocol: Mapped[str | None] = mapped_column(String(32))
    http_method: Mapped[str | None] = mapped_column(String(16))
    http_status: Mapped[int | None] = mapped_column(Integer)
    url_path: Mapped[str | None] = mapped_column(Text)
    user_agent: Mapped[str | None] = mapped_column(Text)
    file_hash: Mapped[str | None] = mapped_column(String(128), index=True)

    __table_args__ = (
        Index("ix_events_case_timeline", "case_id", "timestamp_normalized", "timestamp_confidence", "evidence_file_id", "raw_line_number", "event_id"),
        Index("uq_events_evidence_line", "evidence_file_id", "raw_line_number", unique=True),
    )


class AuditLog(Base):
    __tablename__ = "audit_logs"
    audit_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("cases.case_id", ondelete="RESTRICT"), index=True)
    evidence_file_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("evidence_files.evidence_file_id", ondelete="RESTRICT"))
    action: Mapped[str] = mapped_column(String(128))
    actor: Mapped[str] = mapped_column(String(255), default="system")
    parser_version: Mapped[str | None] = mapped_column(String(64))
    model_version: Mapped[str | None] = mapped_column(String(128))
    prompt_version: Mapped[str | None] = mapped_column(String(64))
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class QuarantinedLine(Base):
    __tablename__ = "quarantined_lines"
    quarantine_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cases.case_id", ondelete="RESTRICT"), index=True)
    evidence_file_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("evidence_files.evidence_file_id", ondelete="CASCADE"), index=True)
    raw_log: Mapped[str] = mapped_column(Text)
    raw_line_number: Mapped[int] = mapped_column(Integer)
    reason_code: Mapped[str] = mapped_column(String(64))
    error_message: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (UniqueConstraint("evidence_file_id", "raw_line_number", name="uq_quarantine_evidence_line"),)


class Correlation(Base):
    __tablename__ = "correlations"
    correlation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cases.case_id", ondelete="RESTRICT"), index=True)
    event_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("events.event_id", ondelete="CASCADE"), index=True)
    related_event_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("events.event_id", ondelete="CASCADE"), index=True)
    entity_type: Mapped[str] = mapped_column(String(32))
    entity_value: Mapped[str] = mapped_column(String(255))
    correlation_reason: Mapped[str] = mapped_column(Text)
    time_delta_seconds: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (Index("uq_correlation_reason", "event_id", "related_event_id", "entity_type", unique=True),)


class Finding(Base):
    __tablename__ = "findings"
    finding_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cases.case_id", ondelete="RESTRICT"), index=True)
    finding_type: Mapped[str] = mapped_column(String(64), index=True)
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text)
    entity_type: Mapped[str] = mapped_column(String(32))
    entity_value: Mapped[str] = mapped_column(String(255))
    first_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    evidence_ids: Mapped[list] = mapped_column(JSON)
    risk_score: Mapped[float] = mapped_column(Float)
    risk_breakdown: Mapped[dict] = mapped_column(JSON)
    confidence_score: Mapped[float] = mapped_column(Float, default=0.5)
    confidence_breakdown: Mapped[dict] = mapped_column(JSON, default=dict)
    mitre_technique: Mapped[str | None] = mapped_column(String(32), index=True)
    mitre_tactic: Mapped[str | None] = mapped_column(String(64))
    false_positive_considerations: Mapped[list] = mapped_column(JSON, default=list)
    recommended_queries: Mapped[list] = mapped_column(JSON, default=list)
    workflow_status: Mapped[str] = mapped_column(String(32), default="new", index=True)
    disposition: Mapped[str | None] = mapped_column(String(64), index=True)
    assigned_to: Mapped[str | None] = mapped_column(String(128), index=True)
    analyst_notes: Mapped[list] = mapped_column(JSON, default=list)
    workflow_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AgentRun(Base):
    __tablename__ = "agent_runs"
    agent_run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cases.case_id", ondelete="CASCADE"), index=True)
    state_version: Mapped[str] = mapped_column(String(32), default="investigation-state-v1")
    status: Mapped[str] = mapped_column(String(32), default="running", index=True)
    question: Mapped[str] = mapped_column(Text)
    state: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


event.listen(
    Event.__table__,
    "after_create",
    DDL("""
    CREATE OR REPLACE FUNCTION prevent_event_evidence_mutation() RETURNS trigger AS $$
    BEGIN
      IF NEW.raw_log IS DISTINCT FROM OLD.raw_log
         OR NEW.raw_line_number IS DISTINCT FROM OLD.raw_line_number
         OR NEW.evidence_file_id IS DISTINCT FROM OLD.evidence_file_id THEN
        RAISE EXCEPTION 'event evidence fields are immutable';
      END IF;
      RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;
    """).execute_if(dialect="postgresql"),
)
event.listen(
    Event.__table__,
    "after_create",
    DDL("""
    CREATE TRIGGER events_evidence_immutable
      BEFORE UPDATE ON events FOR EACH ROW
      EXECUTE FUNCTION prevent_event_evidence_mutation();
    """).execute_if(dialect="postgresql"),
)


@event.listens_for(Event, "before_update")
def prevent_raw_log_update(_mapper, _connection, target: Event) -> None:
    from sqlalchemy import inspect
    state = inspect(target)
    if state.attrs.raw_log.history.has_changes() or state.attrs.raw_line_number.history.has_changes():
        raise ValueError("raw_log and raw_line_number are immutable")
