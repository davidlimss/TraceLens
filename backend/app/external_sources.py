"""Read-only connectors for external security telemetry.

The connectors deliberately accept a small, provider-neutral filter set.  The
agent cannot submit arbitrary OpenSearch DSL, SPL, or Wazuh management calls.
Every returned hit is normalized and later snapshotted as local evidence before
it can be cited by the claim verification gate.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from urllib.parse import quote

import httpx
import redis

from app.config import Settings


class ExternalSourceError(RuntimeError):
    """A safe, user-facing connector failure without credential disclosure."""


ALLOWED_FILTERS = {
    "q", "source_ip", "username", "host", "event_action", "severity",
    "start_time", "end_time", "limit",
}
_SAFE_FIELD = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{0,127}$")


@dataclass(frozen=True)
class ExternalHit:
    provider: str
    source_name: str
    external_event_id: str
    timestamp_original: str | None
    timestamp_normalized: datetime | None
    raw_payload: dict[str, Any]
    raw_log: str
    source_ip: str | None = None
    username: str | None = None
    host: str | None = None
    event_action: str | None = None
    event_outcome: str | None = None
    severity: str = "info"
    tags: list[str] | None = None

    def as_dict(self, evidence_id: uuid.UUID | None = None) -> dict[str, Any]:
        return {
            "evidence_id": str(evidence_id) if evidence_id else None,
            "provider": self.provider,
            "source_name": self.source_name,
            "external_event_id": self.external_event_id,
            "timestamp_original": self.timestamp_original,
            "timestamp_normalized": self.timestamp_normalized.isoformat() if self.timestamp_normalized else None,
            "source_ip": self.source_ip,
            "username": self.username,
            "host": self.host,
            "event_action": self.event_action,
            "event_outcome": self.event_outcome,
            "severity": self.severity,
            "tags": self.tags or [],
            "raw_log": self.raw_log,
        }


def _validate_filters(filters: dict[str, Any] | None, limit: int) -> dict[str, Any]:
    incoming = dict(filters or {})
    unknown = set(incoming) - ALLOWED_FILTERS
    if unknown:
        raise ExternalSourceError(f"unsupported external filter: {sorted(unknown)[0]}")
    if len(str(incoming.get("q", ""))) > 256:
        raise ExternalSourceError("external query text is too long")
    value = max(1, min(int(incoming.get("limit", limit)), limit))
    incoming["limit"] = value
    for key in ("start_time", "end_time"):
        if incoming.get(key):
            try:
                datetime.fromisoformat(str(incoming[key]).replace("Z", "+00:00"))
            except ValueError as exc:
                raise ExternalSourceError(f"invalid {key}") from exc
    return incoming


def _parse_timestamp(value: Any) -> tuple[str | None, datetime | None]:
    if value is None:
        return None, None
    original = str(value)
    try:
        return original, datetime.fromisoformat(original.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return original, None


def _first(payload: dict[str, Any], *paths: str) -> Any:
    for path in paths:
        current: Any = payload
        for part in path.split("."):
            if not isinstance(current, dict) or part not in current:
                current = None
                break
            current = current[part]
        if current not in (None, ""):
            return current
    return None


def _normalize_hit(provider: str, source_name: str, event_id: str, payload: dict[str, Any]) -> ExternalHit:
    timestamp = _first(payload, "@timestamp", "timestamp", "time", "datetime", "_time", "event.created")
    timestamp_original, timestamp_normalized = _parse_timestamp(timestamp)
    outcome = _first(payload, "event.outcome", "outcome", "result", "status")
    severity = str(_first(payload, "severity", "level", "rule.level", "alert_level") or "info").lower()
    if severity.isdigit():
        severity = "critical" if int(severity) >= 12 else "high" if int(severity) >= 8 else "medium" if int(severity) >= 5 else "low"
    raw_log = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return ExternalHit(
        provider=provider, source_name=source_name, external_event_id=event_id,
        timestamp_original=timestamp_original, timestamp_normalized=timestamp_normalized,
        raw_payload=payload, raw_log=raw_log,
        source_ip=str(_first(payload, "source.ip", "src_ip", "srcip", "data.srcip", "clientip") or "") or None,
        username=str(_first(payload, "user.name", "username", "user", "srcuser", "data.srcuser") or "") or None,
        host=str(_first(payload, "host.name", "host", "agent.name", "agent_id", "agent.id") or "") or None,
        event_action=str(_first(payload, "event.action", "action", "event_type", "rule.description", "description") or "") or None,
        event_outcome=str(outcome) if outcome is not None else None,
        severity=severity,
        tags=[str(value) for value in (_first(payload, "tags", "rule.groups") or [])] if isinstance(_first(payload, "tags", "rule.groups"), list) else [],
    )


class _HTTPSource:
    provider = "external"

    def __init__(self, settings: Settings, client: httpx.Client | None = None):
        self.settings = settings
        self.client = client or httpx.Client(timeout=settings.external_search_timeout_seconds)

    def _request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        attempts = max(0, min(int(self.settings.external_max_retries), 3)) + 1
        for attempt in range(attempts):
            try:
                response = self.client.request(method, url, timeout=self.settings.external_search_timeout_seconds, **kwargs)
                response.raise_for_status()
                return response
            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code
                transient = status == 429 or 500 <= status <= 599
                if transient and attempt < attempts - 1:
                    retry_after = exc.response.headers.get("retry-after", "")
                    try:
                        delay = min(float(retry_after), 5.0)
                    except ValueError:
                        delay = min(0.5 * (2 ** attempt), 3.0)
                    time.sleep(delay)
                    continue
                if status in {401, 403}:
                    raise ExternalSourceError(f"{self.provider} credentials rejected") from exc
                raise ExternalSourceError(f"{self.provider} returned HTTP {status}") from exc
            except httpx.HTTPError as exc:
                if attempt < attempts - 1:
                    time.sleep(min(0.5 * (2 ** attempt), 3.0))
                    continue
                raise ExternalSourceError(f"{self.provider} is unavailable") from exc
        raise ExternalSourceError(f"{self.provider} is unavailable")


class OpenSearchSource(_HTTPSource):
    provider = "opensearch"

    def __init__(self, settings: Settings, client: httpx.Client | None = None, *, provider: str = "opensearch", index: str | None = None, url: str | None = None, username: str = "", password: str = "", api_key: str = ""):
        super().__init__(settings, client)
        self.provider = provider
        self.url = (url if url is not None else settings.opensearch_url).rstrip("/")
        self.index = index if index is not None else settings.opensearch_index
        self.username = username or settings.opensearch_username
        self.password = password or settings.opensearch_password
        self.api_key = api_key or settings.opensearch_api_key

    def _headers(self) -> dict[str, str]:
        if self.api_key:
            return {"Authorization": f"ApiKey {self.api_key}", "Content-Type": "application/json"}
        return {"Content-Type": "application/json"}

    def _body(self, case_id: uuid.UUID, filters: dict[str, Any]) -> dict[str, Any]:
        case_field = self.settings.external_case_field
        if not _SAFE_FIELD.fullmatch(case_field):
            raise ExternalSourceError("EXTERNAL_CASE_FIELD contains unsupported characters")
        filters_list: list[dict[str, Any]] = [{"term": {case_field: str(case_id)}}]
        exact_map = {"source_ip": "source.ip", "username": "user.name", "host": "host.name", "event_action": "event.action", "severity": "severity"}
        for key, field in exact_map.items():
            if filters.get(key):
                filters_list.append({"term": {field: str(filters[key])}})
        time_range: dict[str, Any] = {}
        if filters.get("start_time"):
            time_range["gte"] = filters["start_time"]
        if filters.get("end_time"):
            time_range["lte"] = filters["end_time"]
        if time_range:
            filters_list.append({"range": {"@timestamp": time_range}})
        must = [{"multi_match": {"query": str(filters["q"]), "fields": ["message", "event.original", "log.original"], "operator": "and"}}] if filters.get("q") else [{"match_all": {}}]
        return {"size": filters["limit"], "track_total_hits": False, "sort": [{"@timestamp": "asc"}], "query": {"bool": {"must": must, "filter": filters_list}}}

    def search(self, case_id: uuid.UUID, filters: dict[str, Any] | None = None) -> tuple[dict[str, Any], list[ExternalHit]]:
        filters = _validate_filters(filters, self.settings.external_max_results)
        if not self.url or not self.index:
            raise ExternalSourceError(f"{self.provider} is not configured")
        body = self._body(case_id, filters)
        headers = self._headers()
        auth = (self.username, self.password) if self.username else None
        endpoint = f"{self.url}/{quote(self.index, safe='*,-_.,')}/_search"
        response = self._request("POST", endpoint, json=body, headers=headers, auth=auth)
        payload = response.json()
        hits: list[ExternalHit] = []
        for index, item in enumerate(((payload.get("hits") or {}).get("hits") or [])):
            source = item.get("_source") if isinstance(item, dict) else None
            if not isinstance(source, dict):
                continue
            external_id = str(item.get("_id") or hashlib.sha256(json.dumps(source, sort_keys=True, default=str).encode()).hexdigest())
            hits.append(_normalize_hit(self.provider, self.index, external_id, source))
        return {"provider": self.provider, "index": self.index, "request": body}, hits


class WazuhSource(OpenSearchSource):
    provider = "wazuh"

    def __init__(self, settings: Settings, client: httpx.Client | None = None):
        super().__init__(settings, client, provider="wazuh", index=settings.wazuh_index, url=settings.wazuh_indexer_url,
                         username=settings.wazuh_username, password=settings.wazuh_password, api_key=settings.wazuh_api_key)


def _splunk_quote(value: Any) -> str:
    text = str(value)
    if "\n" in text or "\r" in text:
        raise ExternalSourceError("newline is not allowed in external filters")
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


class SplunkSource(_HTTPSource):
    provider = "splunk"

    def search(self, case_id: uuid.UUID, filters: dict[str, Any] | None = None) -> tuple[dict[str, Any], list[ExternalHit]]:
        filters = _validate_filters(filters, self.settings.external_max_results)
        if not self.settings.splunk_url or not self.settings.splunk_index or not self.settings.splunk_token:
            raise ExternalSourceError("splunk is not configured")
        if not _SAFE_FIELD.fullmatch(self.settings.splunk_case_field):
            raise ExternalSourceError("SPLUNK_CASE_FIELD contains unsupported characters")
        conditions = [f"{self.settings.splunk_case_field}={_splunk_quote(case_id)}"]
        for key in ("source_ip", "username", "host", "event_action", "severity"):
            if filters.get(key):
                conditions.append(f"{key}={_splunk_quote(filters[key])}")
        if filters.get("q"):
            conditions.append(_splunk_quote(filters["q"]))
        query = f"search index={_splunk_quote(self.settings.splunk_index)} " + " ".join(conditions) + f" | head {filters['limit']}"
        data = {"search": query, "output_mode": "json", "exec_mode": "oneshot", "count": filters["limit"]}
        if filters.get("start_time"):
            data["earliest_time"] = str(filters["start_time"])
        if filters.get("end_time"):
            data["latest_time"] = str(filters["end_time"])
        endpoint = self.settings.splunk_url.rstrip("/") + "/services/search/jobs/export"
        response = self._request("POST", endpoint, data=data, headers={"Authorization": f"Bearer {self.settings.splunk_token}"})
        rows: list[dict[str, Any]] = []
        content = response.text.strip()
        if content:
            try:
                decoded = response.json()
                if isinstance(decoded, dict):
                    rows = decoded.get("results") or ([decoded["result"]] if isinstance(decoded.get("result"), dict) else [])
                elif isinstance(decoded, list):
                    rows = decoded
            except (ValueError, json.JSONDecodeError):
                for line in content.splitlines():
                    try:
                        item = json.loads(line)
                        if isinstance(item, dict):
                            rows.append(item.get("result", item))
                    except json.JSONDecodeError:
                        continue
        hits = []
        for index, row in enumerate(rows[:filters["limit"]]):
            if not isinstance(row, dict):
                continue
            external_id = str(row.get("_cd") or row.get("_serial") or row.get("event_id") or f"row-{index}")
            hits.append(_normalize_hit("splunk", self.settings.splunk_index, external_id, row))
        return {"provider": "splunk", "index": self.settings.splunk_index, "request": data, "query": query}, hits


class ExternalSourceManager:
    def __init__(self, settings: Settings, client: httpx.Client | None = None):
        self.settings = settings
        self.client = client

    def _redis(self):
        try:
            return redis.Redis.from_url(self.settings.redis_url, socket_timeout=0.5)
        except Exception:
            return None

    def _breaker_key(self, provider: str) -> str:
        return f"tracelens:external:breaker:{provider}"

    def _breaker_open(self, provider: str) -> bool:
        client = self._redis()
        if client is None:
            return False
        try:
            value = client.get(self._breaker_key(provider))
            return int(value or 0) >= self.settings.external_circuit_breaker_threshold
        except (redis.RedisError, TypeError, ValueError):
            return False

    def _record_failure(self, provider: str) -> None:
        client = self._redis()
        if client is None:
            return
        try:
            key = self._breaker_key(provider)
            count = client.incr(key)
            if count == 1:
                client.expire(key, self.settings.external_circuit_breaker_window_seconds)
        except redis.RedisError:
            return

    def _clear_failures(self, provider: str) -> None:
        client = self._redis()
        if client is None:
            return
        try:
            client.delete(self._breaker_key(provider))
        except redis.RedisError:
            return

    def breaker_state(self) -> dict[str, int]:
        client = self._redis()
        if client is None:
            return {}
        state: dict[str, int] = {}
        for provider in ("opensearch", "splunk", "wazuh"):
            try:
                state[provider] = int(client.get(self._breaker_key(provider)) or 0)
            except (redis.RedisError, TypeError, ValueError):
                state[provider] = 0
        return state

    def search(self, provider: str, case_id: uuid.UUID, filters: dict[str, Any] | None = None) -> tuple[dict[str, Any], list[ExternalHit]]:
        if not self.settings.external_sources_enabled:
            raise ExternalSourceError("external sources are disabled")
        provider = provider.lower().strip()
        if provider == "opensearch":
            source = OpenSearchSource(self.settings, self.client, url=self.settings.opensearch_url, index=self.settings.opensearch_index,
                                      username=self.settings.opensearch_username, password=self.settings.opensearch_password, api_key=self.settings.opensearch_api_key)
        elif provider == "wazuh":
            source = WazuhSource(self.settings, self.client)
        elif provider == "splunk":
            source = SplunkSource(self.settings, self.client)
        else:
            raise ExternalSourceError("provider must be opensearch, splunk, or wazuh")
        if self._breaker_open(provider):
            raise ExternalSourceError(f"{provider} temporarily unavailable after repeated upstream failures")
        try:
            request_meta, hits = source.search(case_id, filters)
        except ExternalSourceError:
            self._record_failure(provider)
            raise
        self._clear_failures(provider)
        request_hash = hashlib.sha256(json.dumps(request_meta, sort_keys=True, default=str).encode()).hexdigest()
        return {**request_meta, "query_sha256": request_hash}, hits


def external_source_health(settings: Settings | None = None) -> dict[str, Any]:
    settings = settings or Settings()
    manager = ExternalSourceManager(settings)
    return {
        "enabled": settings.external_sources_enabled,
        "read_only": True,
        "providers": {
            "opensearch": {"configured": bool(settings.opensearch_url and settings.opensearch_index)},
            "splunk": {"configured": bool(settings.splunk_url and settings.splunk_index and settings.splunk_token)},
            "wazuh": {"configured": bool(settings.wazuh_indexer_url and settings.wazuh_index)},
        },
        "circuit_breaker_failures": manager.breaker_state(),
        "retry_policy": {"max_retries": settings.external_max_retries,
                         "timeout_seconds": settings.external_search_timeout_seconds},
    }
