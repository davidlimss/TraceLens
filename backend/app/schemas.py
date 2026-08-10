import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class CaseCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=1, max_length=512)


class CurrentUserRead(BaseModel):
    user_id: uuid.UUID
    username: str
    global_role: str


class CaseRead(CaseCreate):
    model_config = ConfigDict(from_attributes=True)
    case_id: uuid.UUID
    created_at: datetime


class EvidenceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    evidence_file_id: uuid.UUID
    case_id: uuid.UUID
    original_filename: str
    sha256: str
    size_bytes: int
    detected_format: str | None
    status: str
    error_message: str | None = None
    uploaded_at: datetime
    parsed_at: datetime | None = None
    job_id: uuid.UUID | None = None
    parsing_mode: str
    total_lines: int
    processed_lines: int
    parsed_events: int
    malformed_lines: int
    progress_percent: int
    heartbeat_at: datetime | None = None
    completeness_ratio: float
    integrity_status: str | None = None
    integrity_verified_at: datetime | None = None


class EventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    event_id: uuid.UUID
    evidence_file_id: uuid.UUID | None = None
    external_evidence_id: uuid.UUID | None = None
    event_origin: str = "local"
    timestamp_original: str | None
    timestamp_normalized: datetime | None
    timezone: str | None
    source_type: str
    source_name: str
    host: str | None
    event_category: str
    event_action: str
    event_outcome: str | None
    severity: str
    username: str | None
    source_ip: str | None
    destination_ip: str | None
    process_name: str | None
    file_name: str | None
    raw_log: str
    raw_line_number: int | None
    parser_name: str
    parser_confidence: float
    tags: list
    session_id: str | None
    timestamp_confidence: float
    timestamp_assumptions: list
    year_source: str | None
    timezone_source: str | None
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


class EventPage(BaseModel):
    items: list[EventRead]
    page: int
    page_size: int
    total: int


class EventContext(BaseModel):
    event: EventRead
    before: list[EventRead]
    after: list[EventRead]


class ExternalEvidenceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    evidence_id: uuid.UUID
    provider: str
    source_name: str
    external_event_id: str
    timestamp_original: str | None
    timestamp_normalized: datetime | None
    raw_log: str
    raw_line_number: int | None = None
    content_sha256: str
    retrieved_at: datetime
    source_ip: str | None = None
    username: str | None = None
    host: str | None = None
    event_action: str | None = None
    event_outcome: str | None = None
    severity: str = "info"
    tags: list = Field(default_factory=list)


class CorrelationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    correlation_id: uuid.UUID
    event_id: uuid.UUID
    related_event_id: uuid.UUID
    entity_type: str
    entity_value: str
    correlation_reason: str
    time_delta_seconds: int


class TimelineItem(BaseModel):
    event: EventRead
    correlations: list[CorrelationRead]


class TimelinePage(BaseModel):
    items: list[TimelineItem]
    page: int
    page_size: int
    total: int


class EntityRead(BaseModel):
    entity_type: str
    entity_value: str
    event_count: int
    first_seen: datetime | None
    last_seen: datetime | None


class FindingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    finding_id: uuid.UUID
    finding_type: str
    title: str
    description: str
    entity_type: str
    entity_value: str
    first_seen: datetime
    last_seen: datetime
    evidence_ids: list
    risk_score: float
    risk_breakdown: dict
    confidence_score: float = 0.5
    confidence_breakdown: dict = Field(default_factory=dict)
    mitre_technique: str | None = None
    mitre_tactic: str | None = None
    false_positive_considerations: list = Field(default_factory=list)
    recommended_queries: list = Field(default_factory=list)
    workflow_status: str = "new"
    disposition: str | None = None
    assigned_to: str | None = None
    analyst_notes: list = Field(default_factory=list)
    workflow_updated_at: datetime | None = None


class FindingWorkflowUpdate(BaseModel):
    workflow_status: Literal["new", "triaging", "escalated", "contained", "closed"]
    disposition: Literal["true_positive", "benign_positive", "false_positive", "duplicate", "inconclusive"] | None = None
    assigned_to: str | None = Field(default=None, max_length=128)
    note: str | None = Field(default=None, max_length=4000)


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)


class AgentClaim(BaseModel):
    claim_id: str | None = None
    hypothesis_id: str | None = None
    text: str
    status: Literal["fact", "inference", "hypothesis"]
    evidence_id: uuid.UUID
    supporting_evidence_ids: list[uuid.UUID] = Field(default_factory=list)
    contradicting_evidence_ids: list[uuid.UUID] = Field(default_factory=list)
    entities: dict[str, str] = Field(default_factory=dict)
    confidence: float | None = Field(default=None, ge=0, le=1)
    reasoning_summary: str | None = None
    limitations: list[str] = Field(default_factory=list)
    required_additional_evidence: list[str] = Field(default_factory=list)
    verification_status: Literal["verified", "repaired", "rejected"] = "verified"
    verification_reasons: list[str] = Field(default_factory=list)


class ChatResponse(BaseModel):
    answer: str
    claims: list[AgentClaim]
    agent_run_id: uuid.UUID | None = None
    run_status: str = "complete"
    investigation: dict = Field(default_factory=dict)
    verification_summary: dict = Field(default_factory=dict)


class AgentRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    agent_run_id: uuid.UUID
    case_id: uuid.UUID
    state_version: str
    status: str
    question: str
    current_step: int
    cancel_requested: bool
    stop_reason: str | None = None
    prompt_version: str | None = None
    model_version: str | None = None
    graph_version: str
    state_summary: dict = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class AgentStepRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    agent_step_id: uuid.UUID
    agent_run_id: uuid.UUID
    step_number: int
    step_type: str
    name: str
    status: str
    input_data: dict
    output_data: dict
    evidence_ids: list = Field(default_factory=list)
    error_code: str | None = None
    started_at: datetime
    ended_at: datetime | None = None
    latency_ms: int | None = None


class EvidenceLedgerRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    ledger_id: uuid.UUID
    agent_run_id: uuid.UUID
    evidence_id: uuid.UUID
    evidence_kind: str
    source_tool: str
    reference_count: int
    details: dict
    first_seen_at: datetime
    last_seen_at: datetime


class ReplayRequest(BaseModel):
    mode: Literal["deterministic_trace", "model_re_evaluation"] = "deterministic_trace"


class ReportExportRequest(BaseModel):
    format: Literal["markdown", "pdf"]
    acknowledge_warnings: bool = False


class IntegrityVerificationRead(BaseModel):
    evidence_file_id: uuid.UUID
    expected_sha256: str
    actual_sha256: str
    status: Literal["match", "mismatch"]
    verified_at: datetime


class ReportExportResponse(BaseModel):
    export_id: uuid.UUID
    format: Literal["markdown", "pdf"]
    content: str
