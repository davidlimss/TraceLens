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
    # Uploaded events point to an immutable EvidenceFile. External events are
    # canonical projections of ExternalEvidence and therefore have no upload
    # file; both paths still retain an immutable raw snapshot.
    evidence_file_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("evidence_files.evidence_file_id", ondelete="RESTRICT"), index=True, nullable=True)
    external_evidence_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("external_evidence.evidence_id", ondelete="RESTRICT"), index=True, nullable=True)
    event_origin: Mapped[str] = mapped_column(String(32), default="local", index=True)
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
    raw_line_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
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
        UniqueConstraint("external_evidence_id", name="uq_events_external_evidence"),
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
    current_step: Mapped[int] = mapped_column(Integer, default=0)
    cancel_requested: Mapped[bool] = mapped_column(default=False)
    stop_reason: Mapped[str | None] = mapped_column(Text)
    prompt_version: Mapped[str | None] = mapped_column(String(64))
    model_version: Mapped[str | None] = mapped_column(String(128))
    graph_version: Mapped[str] = mapped_column(String(64), default="investigation-graph-v1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AgentRunSnapshot(Base):
    """Frozen operational snapshot used for audit, deterministic replay, and diff."""
    __tablename__ = "agent_run_snapshots"
    snapshot_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("agent_runs.agent_run_id", ondelete="CASCADE"), index=True)
    case_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cases.case_id", ondelete="CASCADE"), index=True)
    source_run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    snapshot_type: Mapped[str] = mapped_column(String(32), default="completion")
    replay_mode: Mapped[str | None] = mapped_column(String(32))
    snapshot_version: Mapped[str] = mapped_column(String(32), default="run-snapshot-v1")
    snapshot_hash: Mapped[str] = mapped_column(String(64), index=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AgentStep(Base):
    """Durable, redacted trace of one model or tool step in an investigation."""
    __tablename__ = "agent_steps"
    agent_step_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("agent_runs.agent_run_id", ondelete="CASCADE"), index=True)
    case_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cases.case_id", ondelete="CASCADE"), index=True)
    step_number: Mapped[int] = mapped_column(Integer)
    step_type: Mapped[str] = mapped_column(String(32))
    name: Mapped[str] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(32), default="completed")
    input_data: Mapped[dict] = mapped_column(JSON, default=dict)
    output_data: Mapped[dict] = mapped_column(JSON, default=dict)
    evidence_ids: Mapped[list] = mapped_column(JSON, default=list)
    error_code: Mapped[str | None] = mapped_column(String(64))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (Index("ix_agent_steps_run_order", "agent_run_id", "step_number", "agent_step_id"),)


class EvidenceLedger(Base):
    """Links an investigation run to evidence it actually observed."""
    __tablename__ = "evidence_ledgers"
    ledger_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("agent_runs.agent_run_id", ondelete="CASCADE"), index=True)
    case_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cases.case_id", ondelete="CASCADE"), index=True)
    evidence_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    evidence_kind: Mapped[str] = mapped_column(String(32))
    source_tool: Mapped[str] = mapped_column(String(128))
    reference_count: Mapped[int] = mapped_column(Integer, default=1)
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (UniqueConstraint("agent_run_id", "evidence_id", name="uq_evidence_ledger_run_evidence"),)


class ExternalEvidence(Base):
    """Immutable snapshot of a read-only external SIEM result.

    External systems remain the source of truth, but a snapshot is required
    before the result can be cited by the claim verification gate.  The UUID
    is therefore a local evidence identifier, not an attacker-controlled ID.
    """
    __tablename__ = "external_evidence"
    evidence_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cases.case_id", ondelete="RESTRICT"), index=True)
    provider: Mapped[str] = mapped_column(String(32), index=True)
    source_name: Mapped[str] = mapped_column(String(255))
    external_event_id: Mapped[str] = mapped_column(String(512))
    timestamp_original: Mapped[str | None] = mapped_column(String(255))
    timestamp_normalized: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    raw_log: Mapped[str] = mapped_column(Text)
    raw_payload: Mapped[dict] = mapped_column(JSON, default=dict)
    content_sha256: Mapped[str] = mapped_column(String(64), index=True)
    query_sha256: Mapped[str] = mapped_column(String(64), index=True)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    source_ip: Mapped[str | None] = mapped_column(String(255), index=True)
    username: Mapped[str | None] = mapped_column(String(255), index=True)
    host: Mapped[str | None] = mapped_column(String(255), index=True)
    event_action: Mapped[str | None] = mapped_column(String(128))
    event_outcome: Mapped[str | None] = mapped_column(String(32))
    severity: Mapped[str] = mapped_column(String(32), default="info")
    tags: Mapped[list] = mapped_column(JSON, default=list)
    __table_args__ = (
        UniqueConstraint("case_id", "provider", "external_event_id", "content_sha256", name="uq_external_evidence_snapshot"),
    )


event.listen(
    ExternalEvidence.__table__,
    "after_create",
    DDL("""
    CREATE OR REPLACE FUNCTION prevent_external_evidence_mutation() RETURNS trigger AS $$
    BEGIN
      IF NEW.raw_log IS DISTINCT FROM OLD.raw_log
         OR NEW.raw_payload IS DISTINCT FROM OLD.raw_payload
         OR NEW.content_sha256 IS DISTINCT FROM OLD.content_sha256
         OR NEW.provider IS DISTINCT FROM OLD.provider
         OR NEW.external_event_id IS DISTINCT FROM OLD.external_event_id THEN
        RAISE EXCEPTION 'external evidence fields are immutable';
      END IF;
      RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;
    """).execute_if(dialect="postgresql"),
)
event.listen(
    ExternalEvidence.__table__,
    "after_create",
    DDL("""
    CREATE TRIGGER external_evidence_immutable
      BEFORE UPDATE ON external_evidence FOR EACH ROW
      EXECUTE FUNCTION prevent_external_evidence_mutation();
    """).execute_if(dialect="postgresql"),
)


event.listen(
    Event.__table__,
    "after_create",
    DDL("""
    CREATE OR REPLACE FUNCTION prevent_event_evidence_mutation() RETURNS trigger AS $$
    BEGIN
         IF NEW.raw_log IS DISTINCT FROM OLD.raw_log
         OR NEW.raw_line_number IS DISTINCT FROM OLD.raw_line_number
         OR NEW.evidence_file_id IS DISTINCT FROM OLD.evidence_file_id
         OR NEW.external_evidence_id IS DISTINCT FROM OLD.external_evidence_id
         OR NEW.event_origin IS DISTINCT FROM OLD.event_origin THEN
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
