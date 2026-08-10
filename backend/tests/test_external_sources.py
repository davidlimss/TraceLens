import json
import uuid
from urllib.parse import parse_qs

import httpx
import pytest

from app.config import Settings
from app.agent_tools import ToolRegistry
from app.agent_tools import _external_event_projection, search_external_events
from app.external_sources import ExternalHit, ExternalSourceError, ExternalSourceManager, OpenSearchSource, SplunkSource
from app.models import ExternalEvidence
from datetime import datetime, timezone


def test_opensearch_query_is_case_scoped_and_normalized():
    case_id = uuid.uuid4()
    seen = {}

    def handler(request: httpx.Request):
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"hits": {"hits": [{"_id": "a-1", "_source": {
            "@timestamp": "2026-07-28T10:00:00Z", "source": {"ip": "10.0.0.5"},
            "user": {"name": "admin"}, "event": {"action": "login", "outcome": "failure"},
            "message": "failed login", "severity": "high"
        }}]}})

    settings = Settings(external_sources_enabled=True, external_case_field="tracelens.case_id",
                        opensearch_url="https://search.example", opensearch_index="security-logs-*")
    client = httpx.Client(transport=httpx.MockTransport(handler))
    meta, hits = OpenSearchSource(settings, client).search(case_id, {"source_ip": "10.0.0.5", "limit": 5})
    assert seen["body"]["query"]["bool"]["filter"][0] == {"term": {"tracelens.case_id": str(case_id)}}
    assert seen["body"]["size"] == 5
    assert meta["index"] == "security-logs-*"
    assert hits[0].source_ip == "10.0.0.5"
    assert hits[0].event_outcome == "failure"
    assert hits[0].severity == "high"


def test_opensearch_rejects_unknown_filter_and_does_not_accept_raw_dsl():
    settings = Settings(external_sources_enabled=True, opensearch_url="https://search.example", opensearch_index="logs")
    source = OpenSearchSource(settings, httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, json={}))))
    with pytest.raises(ExternalSourceError, match="unsupported external filter"):
        source.search(uuid.uuid4(), {"query": {"match_all": {}}})
    body = source._body(uuid.uuid4(), {"q": "ignore previous instructions", "limit": 1})
    assert "query_string" not in json.dumps(body)
    assert body["query"]["bool"]["must"][0]["multi_match"]["fields"]


def test_splunk_ndjson_is_normalized_and_case_scope_is_injected():
    case_id = uuid.uuid4()
    seen = {}

    def handler(request: httpx.Request):
        seen["body"] = request.content.decode()
        return httpx.Response(200, text='{"result":{"_cd":"x-1","_time":"2026-07-28T10:01:00Z","src_ip":"10.0.0.6","user":"root","action":"sudo","level":"12"}}\n')

    settings = Settings(external_sources_enabled=True, splunk_url="https://splunk.example:8089",
                        splunk_index="security", splunk_token="token", splunk_case_field="tracelens_case_id")
    client = httpx.Client(transport=httpx.MockTransport(handler))
    meta, hits = SplunkSource(settings, client).search(case_id, {"event_action": "sudo", "limit": 10})
    form = parse_qs(seen["body"])
    assert f"tracelens_case_id=\"{case_id}\"" in form["search"][0]
    assert "search index=\"security\"" in form["search"][0]
    assert meta["provider"] == "splunk"
    assert hits[0].external_event_id == "x-1"
    assert hits[0].severity == "critical"
    assert hits[0].username == "root"


def test_manager_rejects_disabled_sources_before_network():
    settings = Settings(external_sources_enabled=False)
    with pytest.raises(ExternalSourceError, match="disabled"):
        ExternalSourceManager(settings).search("opensearch", uuid.uuid4(), {})


def test_agent_external_tool_routes_through_private_mcp_bridge(monkeypatch):
    case_id = uuid.uuid4()
    expected = {"provider": "wazuh", "count": 1, "evidence": [{"evidence_id": str(uuid.uuid4())}]}
    monkeypatch.setattr("app.agent_tools._call_external_mcp", lambda active_case, provider, filters: expected)
    result = ToolRegistry(object(), case_id).execute("search_external_events", {"provider": "wazuh", "filters": {"limit": 1}})
    assert result == expected


class ProjectionDB:
    def __init__(self):
        self.items = []

    def scalar(self, _statement):
        return None

    def add(self, item):
        self.items.append(item)

    def flush(self):
        for item in self.items:
            if isinstance(item, ExternalEvidence) and item.evidence_id is None:
                item.evidence_id = uuid.uuid4()
            if getattr(item, "event_id", None) is None and item.__class__.__name__ == "Event":
                item.event_id = uuid.uuid4()


def test_external_snapshot_is_projected_into_canonical_event():
    case_id = uuid.uuid4()
    evidence = ExternalEvidence(
        evidence_id=uuid.uuid4(), case_id=case_id, provider="wazuh", source_name="wazuh-alerts-*",
        external_event_id="alert-1", timestamp_original="2026-07-28T10:00:00Z",
        timestamp_normalized=datetime(2026, 7, 28, 10, 0, tzinfo=timezone.utc),
        raw_log='{"rule":{"description":"login"}}', raw_payload={"message": "failed login"},
        content_sha256="a" * 64, query_sha256="b" * 64, source_ip="192.0.2.10",
        username="admin", host="srv-1", event_action="login", event_outcome="failure",
        severity="high", tags=["authentication"],
    )
    db = ProjectionDB()
    projection = _external_event_projection(db, case_id, evidence)
    assert projection.event_origin == "external"
    assert projection.external_evidence_id == evidence.evidence_id
    assert projection.evidence_file_id is None
    # External snapshots do not originate from an uploaded file; 0 is the
    # canonical "not applicable" sentinel required by the non-null column.
    assert projection.raw_line_number == 0
    assert projection.event_action == "login"


def test_external_search_rebuilds_deterministic_analysis_from_projection(monkeypatch):
    case_id = uuid.uuid4()
    hit = ExternalHit(
        provider="opensearch", source_name="security-*", external_event_id="evt-1",
        timestamp_original="2026-07-28T10:00:00Z",
        timestamp_normalized=datetime(2026, 7, 28, 10, 0, tzinfo=timezone.utc),
        raw_payload={"message": "failed login"}, raw_log='{"message":"failed login"}',
        source_ip="192.0.2.44", username="admin", host="srv-1",
        event_action="login", event_outcome="failure", severity="high",
    )

    class Manager:
        def __init__(self, _settings):
            pass

        def search(self, _provider, _case_id, _filters):
            return {"provider": "opensearch", "index": "security-*", "query_sha256": "q" * 64}, [hit]

    rebuilt = []
    monkeypatch.setattr("app.agent_tools.ExternalSourceManager", Manager)
    monkeypatch.setattr("app.agent_tools.rebuild_case_analysis", lambda db, active_case, settings: rebuilt.append(active_case))
    result = search_external_events(ProjectionDB(), case_id, "opensearch", {}, Settings(external_sources_enabled=True))

    assert result["count"] == 1
    assert result["evidence"][0]["canonical_event_id"]
    assert rebuilt == [case_id]
