"""Deterministic VIGIL replay, immutable snapshot, and descriptive run diff."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import uuid
from typing import Any

from app.models import AgentRun, AgentRunSnapshot
from app.vigil import public_state_summary


SNAPSHOT_VERSION = "run-snapshot-v1"


def canonical_hash(value: Any) -> str:
    serialized = json.dumps(value, sort_keys=True, ensure_ascii=False, default=str, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def snapshot_payload(run: AgentRun, *, steps: list[Any] | None = None,
                     ledger: list[Any] | None = None) -> dict:
    state = run.state or {}
    steps = steps or []
    ledger = ledger or []
    return {
        "run_id": str(run.agent_run_id),
        "case_id": str(run.case_id),
        "question": run.question,
        "status": run.status,
        "stop_reason": run.stop_reason,
        "prompt_version": run.prompt_version,
        "model_version": run.model_version,
        "graph_version": run.graph_version,
        "state_version": run.state_version,
        "state_schema_version": state.get("state_schema_version"),
        "parser_versions": state.get("parser_versions") or [],
        "risk_version": state.get("risk_version"),
        "tool_registry_version": state.get("tool_registry_version", "tool-registry-v1"),
        "investigation": public_state_summary(state),
        "observed_evidence_ids": list(state.get("collected_evidence_ids") or []),
        "final_claim_ids": list(state.get("final_claim_ids") or []),
        "verification_summary": deepcopy(state.get("verification_summary") or {}),
        "tool_trajectory": [
            {
                "step_number": getattr(item, "step_number", None),
                "step_type": getattr(item, "step_type", None),
                "name": getattr(item, "name", None),
                "status": getattr(item, "status", None),
                "evidence_ids": list(getattr(item, "evidence_ids", None) or []),
                "latency_ms": getattr(item, "latency_ms", None),
                "error_code": getattr(item, "error_code", None),
                "input_data": deepcopy(getattr(item, "input_data", None) or {}),
                "output_data": deepcopy(getattr(item, "output_data", None) or {}),
            }
            for item in steps
        ],
        "evidence_ledger": [
            {
                "evidence_id": str(getattr(item, "evidence_id", "")),
                "source_tool": getattr(item, "source_tool", None),
                "evidence_kind": getattr(item, "evidence_kind", None),
                "reference_count": getattr(item, "reference_count", None),
            }
            for item in ledger
        ],
    }


def create_run_snapshot(db: Any, run: AgentRun, *, steps: list[Any] | None = None,
                        ledger: list[Any] | None = None, snapshot_type: str = "completion",
                        replay_mode: str | None = None, source_run_id: uuid.UUID | None = None) -> AgentRunSnapshot:
    payload = snapshot_payload(run, steps=steps, ledger=ledger)
    snapshot = AgentRunSnapshot(
        snapshot_id=uuid.uuid4(),
        agent_run_id=run.agent_run_id,
        case_id=run.case_id,
        source_run_id=source_run_id or run.agent_run_id,
        snapshot_type=snapshot_type,
        replay_mode=replay_mode,
        snapshot_version=SNAPSHOT_VERSION,
        snapshot_hash=canonical_hash(payload),
        payload=payload,
        created_at=datetime.now(timezone.utc),
    )
    db.add(snapshot)
    run.state = {**(run.state or {}), "run_snapshot": {
        "snapshot_version": SNAPSHOT_VERSION,
        "snapshot_hash": snapshot.snapshot_hash,
        "snapshot_id": str(snapshot.snapshot_id),
        "created_at": snapshot.created_at.isoformat(),
    }}
    return snapshot


def deterministic_trace_replay(payload: dict) -> dict:
    """Replay stored operational observations without calling a model/provider."""
    source = deepcopy(payload or {})
    steps = source.get("tool_trajectory") or []
    evidence: list[str] = []
    tool_names: list[str] = []
    transitions = []
    for step in steps:
        if step.get("step_type") == "tool":
            name = str(step.get("name") or "")
            if name:
                tool_names.append(name)
            evidence.extend(str(item) for item in (step.get("evidence_ids") or []))
        input_data = step.get("input_data") or {}
        vigil = input_data.get("_vigil") if isinstance(input_data, dict) else {}
        if isinstance(vigil, dict) and vigil.get("plan_step_id"):
            transitions.append({"plan_step_id": vigil.get("plan_step_id"), "tool": step.get("name")})
    evidence = list(dict.fromkeys(evidence or source.get("observed_evidence_ids") or []))
    result = {
        "mode": "deterministic_trace",
        "source_run_id": source.get("run_id"),
        "case_id": source.get("case_id"),
        "question": source.get("question"),
        "tool_trajectory": tool_names,
        "observed_evidence_ids": evidence,
        "transitions": transitions,
        "stop_reason": source.get("stop_reason"),
        "verification_summary": deepcopy(source.get("verification_summary") or {}),
        "replay_hash": canonical_hash({
            "tool_trajectory": tool_names,
            "observed_evidence_ids": evidence,
            "stop_reason": source.get("stop_reason"),
            "verification_summary": source.get("verification_summary") or {},
        }),
        "llm_called": False,
    }
    return result


def _set(value: Any) -> set[str]:
    if isinstance(value, list):
        return {str(item) for item in value}
    return set()


def diff_runs(left: dict, right: dict) -> dict:
    """Return descriptive differences; never declares a winner."""
    left_tools = list(left.get("tool_trajectory") or [])
    right_tools = list(right.get("tool_trajectory") or [])
    left_evidence = _set(left.get("observed_evidence_ids"))
    right_evidence = _set(right.get("observed_evidence_ids"))
    left_hyp = {str(item.get("hypothesis_id")): item.get("status") for item in (left.get("investigation", {}).get("hypotheses") or [])}
    right_hyp = {str(item.get("hypothesis_id")): item.get("status") for item in (right.get("investigation", {}).get("hypotheses") or [])}
    left_claims = _set(left.get("final_claim_ids"))
    right_claims = _set(right.get("final_claim_ids"))
    return {
        "left_run_id": left.get("run_id"),
        "right_run_id": right.get("run_id"),
        "descriptive": {
            "tool_count": {"left": len(left_tools), "right": len(right_tools), "delta": len(right_tools) - len(left_tools)},
            "tool_names_only_left": sorted(set(str(item.get("name")) for item in left_tools) - set(str(item.get("name")) for item in right_tools)),
            "tool_names_only_right": sorted(set(str(item.get("name")) for item in right_tools) - set(str(item.get("name")) for item in left_tools)),
            "evidence_count": {"left": len(left_evidence), "right": len(right_evidence), "delta": len(right_evidence) - len(left_evidence)},
            "evidence_only_left": sorted(left_evidence - right_evidence),
            "evidence_only_right": sorted(right_evidence - left_evidence),
            "hypothesis_status_changes": {
                key: {"left": left_hyp.get(key), "right": right_hyp.get(key)}
                for key in sorted(set(left_hyp) | set(right_hyp))
                if left_hyp.get(key) != right_hyp.get(key)
            },
            "claim_ids_only_left": sorted(left_claims - right_claims),
            "claim_ids_only_right": sorted(right_claims - left_claims),
            "stop_reason": {"left": left.get("stop_reason"), "right": right.get("stop_reason")},
            "latency_ms": {
                "left": (left.get("investigation", {}).get("cost_accounting") or {}).get("elapsed_ms"),
                "right": (right.get("investigation", {}).get("cost_accounting") or {}).get("elapsed_ms"),
            },
            "cost_accounting": {
                "left": left.get("investigation", {}).get("cost_accounting") or {},
                "right": right.get("investigation", {}).get("cost_accounting") or {},
            },
        },
        "interpretation": "descriptive_only_no_quality_winner",
    }
