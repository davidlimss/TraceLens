"""TraceLens external-evidence MCP server.

Run with ``python -m app.mcp_server`` for a private stdio MCP server.  Keep
stdio behind the backend/orchestrator in production; do not expose a database
or provider credential through a generic MCP server.  All searches are
read-only, case-scoped, and snapshot results into ``external_evidence`` before
returning them.
"""

from __future__ import annotations

import os
import uuid
from typing import Any

from mcp.server.fastmcp import FastMCP
from sqlalchemy import select

from app.agent_tools import search_external_events
from app.config import get_settings
from app.database import SessionLocal
from app.external_sources import external_source_health
from app.models import AuditLog, ExternalEvidence


settings = get_settings()
mcp = FastMCP(
    name="tracelens-external-evidence",
    instructions=(
        "Read-only external security telemetry tools. Results are local immutable evidence snapshots. "
        "Never submit arbitrary DSL/SPL and never use these tools for response actions."
    ),
)


@mcp.tool()
def list_external_sources() -> dict[str, Any]:
    """Return provider availability without returning credentials."""
    result = external_source_health(settings)
    result["case_scope_field"] = settings.external_case_field
    return result


@mcp.tool()
def search_external_events_mcp(case_id: str, provider: str, filters: dict[str, Any] | None = None) -> dict[str, Any]:
    """Search a configured OpenSearch, Splunk, or Wazuh source."""
    case_uuid = uuid.UUID(case_id)
    with SessionLocal() as db:
        result = search_external_events(db, case_uuid, provider, filters, settings)
        db.add(AuditLog(case_id=case_uuid, action="external_evidence_search", actor="mcp-service",
                        details={"provider": provider, "query_sha256": result.get("query_sha256"),
                                 "count": result.get("count", 0), "filters": {key: value for key, value in (filters or {}).items() if key != "q"}}))
        db.commit()
        return result


@mcp.tool()
def get_external_evidence_mcp(case_id: str, evidence_id: str) -> dict[str, Any]:
    """Retrieve one local external snapshot by evidence ID."""
    case_uuid, evidence_uuid = uuid.UUID(case_id), uuid.UUID(evidence_id)
    with SessionLocal() as db:
        row = db.scalar(select(ExternalEvidence).where(
            ExternalEvidence.case_id == case_uuid, ExternalEvidence.evidence_id == evidence_uuid))
        if row is None:
            raise ValueError("external evidence not found in active case")
        return {
            "evidence_id": str(row.evidence_id), "provider": row.provider,
            "source_name": row.source_name, "external_event_id": row.external_event_id,
            "raw_log": row.raw_log, "content_sha256": row.content_sha256,
            "retrieved_at": row.retrieved_at.isoformat(),
        }


if __name__ == "__main__":
    transport = os.getenv("MCP_TRANSPORT", "stdio")
    if transport == "streamable-http":
        mcp.run(transport="streamable-http")
    else:
        mcp.run(transport="stdio")
