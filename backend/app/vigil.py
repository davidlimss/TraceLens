"""Bounded, auditable investigation state for TraceLens VIGIL.

This module deliberately contains no LLM calls.  It validates and advances
operational state around the existing single-agent tool loop.
"""

from __future__ import annotations

from copy import deepcopy
import re
import uuid
from datetime import datetime, timezone
from typing import Any

from app.vigil_policy import (
    InvestigationPolicy,
    ensure_lifecycle,
    lifecycle_state,
    rank_actions,
    score_action,
    transition_state,
)


STATE_SCHEMA_VERSION = "vigil-state-v2"
PLAN_SCHEMA_VERSION = "investigation-plan-v1"
MAX_ACTION_HISTORY = 100
MAX_OBSERVED_EVIDENCE = 500
MAX_HYPOTHESES = 8
MAX_GAPS = 24
MAX_PROVENANCE = 1000
MAX_TRANSITIONS = 100
MAX_CANDIDATE_ACTIONS = 24

PLAN_STATUSES = {"pending", "active", "completed", "skipped", "blocked", "failed"}
HYPOTHESIS_STATUSES = {"proposed", "investigating", "supported", "weakened", "refuted", "unresolved"}
STOP_REASONS = {
    "GOAL_SATISFIED",
    "EVIDENCE_EXHAUSTED",
    "INSUFFICIENT_EVIDENCE",
    "TOOL_BUDGET_EXHAUSTED",
    "TIME_BUDGET_EXHAUSTED",
    "NO_PROGRESS",
    "USER_PAUSED",
    "USER_CANCELLED",
    "PROVIDER_FAILURE",
    "VERIFICATION_FAILED",
}
ALLOWED_PLAN_TOOLS = {
    "search_events", "search_disconfirming_evidence", "get_surrounding_events",
    "build_timeline", "correlate_entities", "get_raw_evidence", "generate_case_summary",
    "get_external_source_status", "search_external_events",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _uuid_strings(values: Any, allowed: set[str] | None = None, limit: int = MAX_OBSERVED_EVIDENCE) -> list[str]:
    if isinstance(values, (str, uuid.UUID)):
        values = [values]
    if not isinstance(values, list):
        return []
    result: list[str] = []
    for value in values:
        try:
            item = str(uuid.UUID(str(value)))
        except (ValueError, TypeError, AttributeError):
            continue
        if allowed is not None and item not in allowed:
            continue
        if item not in result:
            result.append(item)
        if len(result) >= limit:
            break
    return result


def collect_evidence_ids(value: Any, limit: int = MAX_OBSERVED_EVIDENCE) -> list[str]:
    found: list[str] = []

    def visit(item: Any) -> None:
        if len(found) >= limit:
            return
        if isinstance(item, dict):
            for key, child in item.items():
                if key in {"evidence_id", "event_id", "target_evidence_id", "canonical_event_id"}:
                    try:
                        candidate = str(uuid.UUID(str(child)))
                    except (ValueError, TypeError, AttributeError):
                        candidate = None
                    if candidate and candidate not in found:
                        found.append(candidate)
                else:
                    visit(child)
        elif isinstance(item, list):
            for child in item:
                visit(child)

    visit(value)
    return found


def _step(step_id: str, objective: str, tools: list[str], expected: list[str], dependencies: list[str] | None = None) -> dict:
    return {
        "step_id": step_id,
        "objective": objective,
        "status": "pending",
        "suggested_tools": tools,
        "expected_evidence": expected,
        "dependencies": dependencies or [],
        "status_reason": None,
    }


def create_investigation_plan(question: str, max_revisions: int = 3) -> dict:
    """Create a bounded operational plan without using an LLM."""
    text = str(question or "").strip()
    auth_focus = bool(re.search(r"login|auth|ssh|sudo|password|gagal|berhasil|akun", text, re.I))
    evidence_focus = bool(re.search(r"bukti|evidence|raw|baris|line", text, re.I))
    if auth_focus:
        steps = [
            _step("step-001", "Identifikasi event authentication dan sumber yang dominan",
                  ["search_events"], ["authentication events", "source IP", "username"]),
            _step("step-002", "Susun kronologi authentication secara deterministik",
                  ["build_timeline", "get_surrounding_events"], ["ordered events", "timestamps"]),
            _step("step-003", "Korelasi source IP, username, dan session",
                  ["correlate_entities", "search_events"], ["correlation reason", "shared entities"]),
            _step("step-004", "Cari event yang melemahkan atau menjelaskan alternatif",
                  ["search_disconfirming_evidence", "search_events"], ["maintenance", "scanner", "benign context"]),
            _step("step-005", "Verifikasi claim dan tentukan kecukupan bukti",
                  ["generate_case_summary", "get_raw_evidence"], ["claim evidence", "limitations"]),
        ]
        questions = [
            "Sumber dan user mana yang terlibat?",
            "Apakah ada pola failure berulang?",
            "Apakah terdapat success setelah failure?",
            "Apakah ada penjelasan benign atau bukti kontradiktif?",
        ]
    else:
        steps = [
            _step("step-001", "Ambil ringkasan atau evidence yang diminta investigator",
                  ["get_raw_evidence" if evidence_focus else "generate_case_summary"],
                  ["raw evidence" if evidence_focus else "findings", "risk breakdown"]),
            _step("step-002", "Susun timeline event secara deterministik",
                  ["build_timeline"], ["ordered events", "timestamps"]),
            _step("step-003", "Periksa entity dan konteks sekitar event penting",
                  ["search_events", "correlate_entities", "get_surrounding_events"], ["entities", "context"]),
            _step("step-004", "Cari bukti yang melemahkan interpretasi awal",
                  ["search_disconfirming_evidence", "search_events"], ["contradicting evidence", "alternative"]),
            _step("step-005", "Verifikasi claim dan gap",
                  ["get_raw_evidence", "generate_case_summary"], ["claim evidence", "limitations"]),
        ]
        questions = [
            "Apa event dan finding utama?",
            "Entity apa yang menghubungkan event?",
            "Apa bukti pendukung dan kontradiktif?",
            "Apa yang masih belum dapat dipastikan?",
        ]
    return {
        "plan_schema_version": PLAN_SCHEMA_VERSION,
        "revision": 0,
        "max_revisions": max(0, min(int(max_revisions), 10)),
        "investigation_goal": text,
        "questions": questions,
        "steps": steps,
        "stop_conditions": [
            "goal_satisfied",
            "evidence_exhausted",
            "insufficient_evidence",
            "tool_budget_exhausted",
            "verification_failed",
        ],
        "revision_history": [],
    }


def initial_vigil_state(case_id: uuid.UUID | str, question: str, tool_budget: int,
                        max_revisions: int = 3, max_repairs: int = 2) -> dict:
    plan = create_investigation_plan(question, max_revisions=max_revisions)
    return {
        "state_schema_version": STATE_SCHEMA_VERSION,
        "current_state": "INITIALIZED",
        "lifecycle": {
            "state_machine_version": "vigil-state-machine-v1",
            "current_state": "INITIALIZED",
            "previous_state": None,
            "transition_reason": "RUN_CREATED",
            "transition_timestamp": _utc_now(),
            "transition_version": "v1",
            "transition_history": [],
        },
        "case_id": str(case_id),
        "question": str(question),
        "investigation_goal": str(question),
        "plan": plan,
        "hypotheses": [],
        "hypothesis_competition": {},
        "evidence_gaps": [],
        "epistemic_state": {
            "confirmed_facts": [],
            "active_hypotheses": [],
            "rejected_hypotheses": [],
            "unknowns": [str(question)],
            "evidence_gaps": [],
            "alternative_explanations": [],
            "observed_evidence_ids": [],
            "remaining_budget": {"tool_calls": int(tool_budget)},
            "next_action": None,
        },
        "repair_state": {"attempts": [], "max_attempts": max(0, min(int(max_repairs), 3))},
        "case_memory": {
            "memory_schema_version": "case-memory-v1",
            "case_id": str(case_id),
            "confirmed_entities": [],
            "known_benign_patterns": [],
            "rejected_hypotheses": [],
            "resolved_questions": [],
            "unresolved_questions": [str(question)],
            "relevant_evidence_ids": [],
        },
        "provenance": [],
        "stop_state": {"reason": None, "detail": None, "decided_at": None},
        "completed_steps": [],
        "open_questions": [str(question)],
        "collected_evidence_ids": [],
        "action_history": [],
        "next_action": None,
        "candidate_actions": [],
        "action_ranking": {"version": "next-action-score-v1", "selected_action": None},
        "tool_call_count": 0,
        "remaining_tool_budget": int(tool_budget),
        "cost_accounting": {
            "model_calls": 0, "tool_calls": 0, "tool_result_bytes": 0,
            "input_tokens": None, "output_tokens": None, "estimated_cost": None,
            "external_source_calls": 0, "repair_count": 0, "plan_revision_count": 0,
            "elapsed_ms": 0,
        },
        "progress": {
            "last_signal": "RUN_CREATED", "signal_count": 0, "no_progress_count": 0,
            "useful_evidence_ids": [], "resolved_gap_ids": [], "new_contradiction_ids": [],
        },
        "evidence_quality": {},
        "contradiction_matrix": {},
        "run_snapshot": None,
    }


def ensure_vigil_state(existing: dict | None, case_id: uuid.UUID | str, question: str,
                       tool_budget: int, max_revisions: int = 3, max_repairs: int = 2) -> dict:
    active_case_id = str(case_id)
    if isinstance(existing, dict) and existing.get("case_id") and str(existing.get("case_id")) != active_case_id:
        # Never carry hypotheses, memory, evidence IDs, or provenance across cases.
        existing = None
    state = deepcopy(existing or {})
    if state.get("state_schema_version") != STATE_SCHEMA_VERSION:
        legacy_hypotheses = state.get("hypotheses") if isinstance(state.get("hypotheses"), list) else []
        base = initial_vigil_state(case_id, question, tool_budget, max_revisions, max_repairs)
        state = {**base, **state, "state_schema_version": STATE_SCHEMA_VERSION}
        normalized_legacy = []
        for index, item in enumerate(legacy_hypotheses[:MAX_HYPOTHESES], 1):
            if isinstance(item, str) and item.strip():
                normalized_legacy.append({
                    "hypothesis_id": f"H-{index:03d}", "statement": item.strip(),
                    "status": "investigating", "supporting_evidence_ids": [],
                    "contradicting_evidence_ids": [], "neutral_evidence_ids": [], "missing_evidence": [],
                    "alternative_explanations": [], "confidence": 0.4,
                    "history": [],
                })
            elif isinstance(item, dict):
                normalized_legacy.append(item)
        state["hypotheses"] = normalized_legacy
    state["case_id"] = active_case_id
    ensure_lifecycle(state)
    state.setdefault("question", str(question))
    state.setdefault("plan", create_investigation_plan(question, max_revisions))
    state.setdefault("hypotheses", [])
    state.setdefault("hypothesis_competition", {})
    state.setdefault("evidence_gaps", [])
    state.setdefault("epistemic_state", {})
    state.setdefault("repair_state", {"attempts": [], "max_attempts": max_repairs})
    state.setdefault("case_memory", {
        "memory_schema_version": "case-memory-v1", "case_id": str(case_id),
        "confirmed_entities": [], "known_benign_patterns": [], "rejected_hypotheses": [],
        "resolved_questions": [], "unresolved_questions": [str(question)],
        "relevant_evidence_ids": [],
    })
    if str((state.get("case_memory") or {}).get("case_id") or active_case_id) != active_case_id:
        state["case_memory"] = initial_vigil_state(case_id, question, tool_budget, max_revisions, max_repairs)["case_memory"]
        state["provenance"] = []
    state.setdefault("provenance", [])
    state.setdefault("stop_state", {"reason": None, "detail": None, "decided_at": None})
    state.setdefault("action_history", [])
    state.setdefault("collected_evidence_ids", [])
    state.setdefault("completed_steps", [])
    state.setdefault("candidate_actions", [])
    state.setdefault("action_ranking", {"version": "next-action-score-v1", "selected_action": None})
    state.setdefault("cost_accounting", {
        "model_calls": 0, "tool_calls": int(state.get("tool_call_count") or 0),
        "tool_result_bytes": 0, "input_tokens": None, "output_tokens": None,
        "estimated_cost": None, "external_source_calls": 0, "repair_count": 0,
        "plan_revision_count": int((state.get("plan") or {}).get("revision") or 0), "elapsed_ms": 0,
    })
    state.setdefault("progress", {
        "last_signal": "STATE_RESTORED", "signal_count": 0, "no_progress_count": 0,
        "useful_evidence_ids": [], "resolved_gap_ids": [], "new_contradiction_ids": [],
    })
    state.setdefault("evidence_quality", {})
    state.setdefault("contradiction_matrix", {})
    state.setdefault("run_snapshot", None)
    return state


def advance_lifecycle(state: dict, target: str, reason: str, *, replay: bool = False) -> dict:
    """Apply one explicit state-machine transition or raise InvalidTransition."""
    return transition_state(state, target, reason, replay=replay)


def build_investigation_policy(tool_budget: int, max_revisions: int = 3,
                               max_repairs: int = 2, max_repetition: int = 2) -> InvestigationPolicy:
    return InvestigationPolicy(
        allowed_tools=ALLOWED_PLAN_TOOLS,
        max_tool_calls=tool_budget,
        max_revisions=max_revisions,
        max_repairs=max_repairs,
        max_same_tool_repetition=max_repetition,
    )


def record_evidence_quality(state: dict, evidence_id: str, *, integrity_status: str = "unknown",
                            parser_quality: float | None = None, timestamp_quality: float | None = None,
                            directness: str = "unknown", source_type: str = "unknown",
                            completeness: float | None = None, corroborated: bool = False,
                            quality_flags: list[str] | None = None) -> None:
    """Store descriptive evidence quality, never an attack/truth probability."""
    try:
        normalized = str(uuid.UUID(str(evidence_id)))
    except (ValueError, TypeError, AttributeError):
        return
    def bounded(value: float | None) -> float | None:
        if value is None:
            return None
        return max(0.0, min(1.0, float(value)))
    state.setdefault("evidence_quality", {})[normalized] = {
        "evidence_id": normalized,
        "integrity_status": str(integrity_status),
        "parser_quality": bounded(parser_quality),
        "timestamp_quality": bounded(timestamp_quality),
        "directness": str(directness),
        "source_type": str(source_type),
        "completeness": bounded(completeness),
        "corroborated": bool(corroborated),
        "quality_flags": [str(item)[:100] for item in (quality_flags or [])[:16]],
        "quality_semantics": "evidence_descriptiveness_not_attack_probability",
    }


def build_contradiction_matrix(state: dict) -> dict:
    """Build explicit SUPPORTS/CONTRADICTS/NEUTRAL/UNKNOWN relations."""
    observed = set(state.get("collected_evidence_ids") or [])
    matrix: dict[str, list[dict]] = {}
    for hypothesis in (state.get("hypotheses") or [])[:MAX_HYPOTHESES]:
        hypothesis_id = str(hypothesis.get("hypothesis_id") or "")
        if not hypothesis_id:
            continue
        supports = set(hypothesis.get("supporting_evidence_ids") or [])
        contradicts = set(hypothesis.get("contradicting_evidence_ids") or [])
        neutral = set(hypothesis.get("neutral_evidence_ids") or [])
        relations = []
        for evidence_id in sorted(observed | supports | contradicts | neutral):
            if evidence_id in supports:
                relation, reason = "SUPPORTS", "EXPLICIT_SUPPORTING_EVIDENCE"
            elif evidence_id in contradicts:
                relation, reason = "CONTRADICTS", "EXPLICIT_CONTRADICTING_EVIDENCE"
            elif evidence_id in neutral:
                relation, reason = "NEUTRAL", "EXPLICIT_NEUTRAL_EVIDENCE"
            else:
                relation, reason = "UNKNOWN", "NO_EXPLICIT_RELATION"
            relations.append({"evidence_id": evidence_id, "relation": relation, "reason_code": reason})
        matrix[hypothesis_id] = relations
    state["contradiction_matrix"] = matrix
    return matrix


def mark_progress(state: dict, *, signal: str, evidence_ids: list[str] | None = None,
                  gap_ids: list[str] | None = None, contradiction_ids: list[str] | None = None,
                  useful: bool = True) -> None:
    progress = state.setdefault("progress", {})
    evidence_ids = list(evidence_ids or [])
    if useful:
        progress["signal_count"] = int(progress.get("signal_count") or 0) + 1
        progress["no_progress_count"] = 0
    else:
        progress["no_progress_count"] = int(progress.get("no_progress_count") or 0) + 1
    progress["last_signal"] = str(signal)
    for key, values in (("useful_evidence_ids", evidence_ids), ("resolved_gap_ids", gap_ids or []),
                        ("new_contradiction_ids", contradiction_ids or [])):
        progress[key] = list(dict.fromkeys([*(progress.get(key) or []), *[str(item) for item in values]]))[-MAX_OBSERVED_EVIDENCE:]


def record_provenance(state: dict, source_type: str, source_id: str,
                      target_type: str, target_id: str, relation: str,
                      step_id: str | None = None, metadata: dict | None = None) -> None:
    """Append a bounded, case-local provenance edge without storing reasoning."""
    relation_item = {
        "source_type": str(source_type), "source_id": str(source_id),
        "target_type": str(target_type), "target_id": str(target_id),
        "relation": str(relation), "step_id": step_id,
        "metadata": {str(k): str(v)[:200] for k, v in (metadata or {}).items()},
        "at": _utc_now(),
    }
    edges = state.setdefault("provenance", [])
    fingerprint = (relation_item["source_type"], relation_item["source_id"],
                   relation_item["target_type"], relation_item["target_id"], relation_item["relation"])
    if not any((item.get("source_type"), item.get("source_id"), item.get("target_type"),
                item.get("target_id"), item.get("relation")) == fingerprint for item in edges):
        edges.append(relation_item)
    state["provenance"] = edges[-MAX_PROVENANCE:]


def revise_plan(state: dict, updates: list[dict], reason: str) -> bool:
    """Apply a bounded operational plan revision; reject write/action tools."""
    plan = state.get("plan") or {}
    revision = int(plan.get("revision") or 0)
    if revision >= int(plan.get("max_revisions") or 0):
        return False
    by_id = {item.get("step_id"): item for item in plan.get("steps") or []}
    changed = []
    for update in (updates or [])[:len(by_id)]:
        if not isinstance(update, dict) or update.get("step_id") not in by_id:
            continue
        step = by_id[update["step_id"]]
        tools = [str(tool) for tool in (update.get("suggested_tools") or step.get("suggested_tools") or [])]
        if any(tool not in ALLOWED_PLAN_TOOLS for tool in tools):
            continue
        before = {"objective": step.get("objective"), "suggested_tools": step.get("suggested_tools"),
                  "status": step.get("status")}
        for key in ("objective", "expected_evidence", "dependencies", "status"):
            if key in update and key != "status":
                step[key] = update[key]
            elif key == "status" and update.get(key) in PLAN_STATUSES:
                step[key] = update[key]
        step["suggested_tools"] = tools
        step["status_reason"] = str(reason)[:300]
        changed.append({"step_id": step["step_id"], "before": before,
                        "after": {"objective": step.get("objective"), "suggested_tools": step.get("suggested_tools"), "status": step.get("status")}})
    if not changed:
        return False
    plan["revision"] = revision + 1
    plan.setdefault("revision_history", []).append({"revision": plan["revision"], "reason": str(reason)[:300], "changes": changed, "at": _utc_now()})
    plan["revision_history"] = plan["revision_history"][-10:]
    state.setdefault("cost_accounting", {})["plan_revision_count"] = plan["revision"]
    return True


def _plan_step_for_tool(state: dict, tool_name: str) -> dict | None:
    steps = ((state.get("plan") or {}).get("steps") or [])
    for item in steps:
        if item.get("status") in {"pending", "active"} and tool_name in (item.get("suggested_tools") or []):
            return item
    for item in steps:
        if item.get("status") in {"pending", "active"}:
            return item
    return None


def _finalize_action(state: dict, action: dict, *, gap_priority: str = "medium",
                     hypothesis_relevance: float = 0.5, expected_value: float = 0.5,
                     reason_codes: list[str] | None = None) -> dict:
    candidate = {
        "candidate_action": action.get("action"),
        "gap_priority": gap_priority,
        "hypothesis_relevance": hypothesis_relevance,
        "expected_evidence_value": expected_value,
        "source_diversity_bonus": 0.1 if action.get("action") in {"search_disconfirming_evidence", "search_external_events"} else 0.0,
        "novelty_bonus": 0.1 if action.get("action") not in {item.get("action") for item in (state.get("action_history") or [])[-5:]} else 0.0,
        "estimated_cost": 2 if action.get("action") in {"get_raw_evidence", "search_external_events"} else 1,
        "repeat_penalty": 0.2 if action.get("action") in {item.get("action") for item in (state.get("action_history") or [])[-3:]} else 0.0,
        "reason_codes": reason_codes or [str(action.get("reason_code") or "ACTION_SELECTED")],
    }
    candidates = [candidate]
    for gap in (state.get("evidence_gaps") or [])[:MAX_GAPS]:
        if gap.get("status", "open") != "open":
            continue
        for tool in (gap.get("candidate_tools") or ["search_events"])[:3]:
            candidates.append({
                "candidate_action": str(tool), "target_gap": gap.get("gap_id"),
                "target_hypothesis": gap.get("hypothesis_id"),
                "gap_priority": gap.get("priority", "medium"),
                "hypothesis_relevance": 0.8 if gap.get("hypothesis_id") else 0.5,
                "expected_evidence_value": 0.8 if tool == "search_disconfirming_evidence" else 0.6,
                "estimated_cost": 2 if tool in {"get_raw_evidence", "search_external_events"} else 1,
                "reason_codes": ["OPEN_EVIDENCE_GAP"],
            })
    for step in (state.get("plan", {}).get("steps") or []):
        if step.get("status") in {"pending", "active"}:
            for tool in (step.get("suggested_tools") or [])[:2]:
                candidates.append({
                    "candidate_action": str(tool), "plan_step_id": step.get("step_id"),
                    "gap_priority": "medium", "hypothesis_relevance": 0.5,
                    "expected_evidence_value": 0.5, "estimated_cost": 1,
                    "reason_codes": ["PENDING_PLAN_STEP"],
                })
    deduped = {(str(item.get("candidate_action")), str(item.get("target_gap")), str(item.get("plan_step_id"))): item
               for item in candidates}
    ranked = rank_actions(list(deduped.values()), remaining_budget=int(state.get("remaining_tool_budget") or 0))
    scored = ranked[0] if ranked else candidate
    action["score"] = scored.get("score", 0.0)
    action["estimated_cost"] = scored.get("estimated_cost", 1)
    action["reason_codes"] = scored.get("reason_codes", [])
    state["candidate_actions"] = ranked[:MAX_CANDIDATE_ACTIONS]
    state["action_ranking"] = {
        "version": "next-action-score-v1",
        "selected_action": action.get("action"),
        "selected_score": action.get("score"),
        "candidates": ranked[:MAX_CANDIDATE_ACTIONS],
    }
    return action


def select_next_action(state: dict) -> dict:
    def activate(step_id: str | None) -> None:
        if not step_id:
            return
        for plan_step in (state.get("plan", {}).get("steps") or []):
            if plan_step.get("step_id") == step_id and plan_step.get("status") == "pending":
                plan_step["status"] = "active"
                plan_step["status_reason"] = "selected_by_bounded_gap_policy"

    gaps = state.get("evidence_gaps") or []
    priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    pending_gaps = [item for item in gaps if item.get("status", "open") == "open"]
    if pending_gaps:
        gap = sorted(pending_gaps, key=lambda item: (priority_order.get(item.get("priority"), 9), item.get("gap_id", "")))[0]
        tool = (gap.get("candidate_tools") or ["search_events"])[0]
        action = {
            "action": tool,
            "reason_code": "RESOLVE_EVIDENCE_GAP",
            "target_gap": gap.get("gap_id"),
            "target_hypothesis": gap.get("hypothesis_id"),
            "plan_step_id": gap.get("plan_step_id"),
        }
        activate(action.get("plan_step_id"))
        return _finalize_action(state, action, gap_priority=str(gap.get("priority") or "medium"),
                                hypothesis_relevance=0.8, expected_value=0.8,
                                reason_codes=["HIGH_PRIORITY_GAP" if gap.get("priority") in {"critical", "high"} else "OPEN_EVIDENCE_GAP"])
    step = next((item for item in (state.get("plan") or {}).get("steps", [])
                 if item.get("status") in {"pending", "active"}), None)
    if step is not None:
        action = {
            "action": (step.get("suggested_tools") or ["generate_case_summary"])[0],
            "reason_code": "EXECUTE_PLAN_STEP",
            "plan_step_id": step.get("step_id"),
            "target_gap": None,
            "target_hypothesis": None,
        }
        activate(action.get("plan_step_id"))
        return _finalize_action(state, action, gap_priority="medium", hypothesis_relevance=0.5,
                                expected_value=0.5, reason_codes=["EXECUTE_PLAN_STEP"])
    return _finalize_action(state, {
        "action": "verify_claims",
        "reason_code": "VERIFY_FINAL_CLAIMS",
        "plan_step_id": None,
        "target_gap": None,
        "target_hypothesis": None,
    }, gap_priority="low", hypothesis_relevance=0.3, expected_value=0.4,
    reason_codes=["VERIFY_FINAL_CLAIMS"])


def analyze_evidence_gaps(state: dict) -> list[dict]:
    gaps: list[dict] = []
    hypotheses = state.get("hypotheses") or []
    for hypothesis in hypotheses[:MAX_HYPOTHESES]:
        status = hypothesis.get("status")
        if status not in {"proposed", "investigating", "supported"}:
            continue
        hypothesis_id = hypothesis.get("hypothesis_id")
        supporting = hypothesis.get("supporting_evidence_ids") or []
        contradicting = hypothesis.get("contradicting_evidence_ids") or []
        if not supporting:
            gaps.append({
                "gap_id": f"gap-{hypothesis_id}-support",
                "hypothesis_id": hypothesis_id,
                "description": "Belum ada evidence yang mendukung hypothesis secara langsung.",
                "priority": "high",
                "candidate_tools": ["search_events", "get_surrounding_events"],
                "status": "open",
                "plan_step_id": "step-001",
            })
        if not contradicting:
            gaps.append({
                "gap_id": f"gap-{hypothesis_id}-contradiction",
                "hypothesis_id": hypothesis_id,
                "description": "Belum ada pencarian evidence yang dapat melemahkan atau membantah hypothesis.",
                "priority": "medium",
                "candidate_tools": ["search_disconfirming_evidence", "search_events"],
                "status": "open",
                "plan_step_id": "step-004",
            })
        for index, missing in enumerate((hypothesis.get("missing_evidence") or [])[:5], 1):
            gaps.append({
                "gap_id": f"gap-{hypothesis_id}-missing-{index}",
                "hypothesis_id": hypothesis_id,
                "description": str(missing),
                "priority": "high",
                "candidate_tools": ["search_events", "get_surrounding_events"],
                "status": "open",
                "plan_step_id": "step-004",
            })
    for item in (state.get("evidence_gaps") or []):
        if item.get("gap_id") not in {gap.get("gap_id") for gap in gaps} and item.get("status") == "open":
            gaps.append(item)
    return gaps[:MAX_GAPS]


def merge_hypotheses(state: dict, raw_hypotheses: Any, observed_ids: set[str] | None = None) -> None:
    if not isinstance(raw_hypotheses, list):
        return
    observed_ids = observed_ids or set(state.get("collected_evidence_ids") or [])
    by_id = {item.get("hypothesis_id"): item for item in state.get("hypotheses", []) if isinstance(item, dict)}
    for index, raw in enumerate(raw_hypotheses[:MAX_HYPOTHESES], 1):
        if not isinstance(raw, dict):
            continue
        statement = str(raw.get("statement") or raw.get("text") or "").strip()
        if not statement:
            continue
        hypothesis_id = str(raw.get("hypothesis_id") or f"H-{len(by_id) + index:03d}")
        status = str(raw.get("status") or "proposed").lower()
        if status not in HYPOTHESIS_STATUSES:
            status = "proposed"
        support = _uuid_strings(raw.get("supporting_evidence_ids"), observed_ids)
        contradicting = _uuid_strings(raw.get("contradicting_evidence_ids"), observed_ids)
        neutral = _uuid_strings(raw.get("neutral_evidence_ids"), observed_ids)
        confidence = raw.get("confidence", 0.4)
        try:
            confidence = max(0.0, min(float(confidence), 1.0))
        except (ValueError, TypeError):
            confidence = 0.4
        previous = by_id.get(hypothesis_id)
        history = list((previous or {}).get("history") or [])[-19:]
        previous_status = (previous or {}).get("status")
        revision = int((previous or {}).get("revision") or 0)
        trigger_ids = list(dict.fromkeys([*support, *contradicting, *neutral]))
        if previous and (previous_status != status or set(previous.get("supporting_evidence_ids") or []) != set(support)
                         or set(previous.get("contradicting_evidence_ids") or []) != set(contradicting)
                         or set(previous.get("neutral_evidence_ids") or []) != set(neutral)):
            revision += 1
            reason_code = "CONTRADICTORY_EVIDENCE" if contradicting else "SUPPORTING_EVIDENCE_UPDATED"
            history.append({"revision": revision, "previous_status": previous_status, "new_status": status,
                            "from": previous_status, "to": status,
                            "trigger_evidence_ids": trigger_ids[:32], "reason_code": reason_code, "at": _utc_now()})
        by_id[hypothesis_id] = {
            "hypothesis_id": hypothesis_id,
            "statement": statement[:1000],
            "status": status,
            "competition_group": str(raw.get("competition_group") or (previous or {}).get("competition_group") or "default"),
            "supporting_evidence_ids": support,
            "contradicting_evidence_ids": contradicting,
            "neutral_evidence_ids": neutral,
            "missing_evidence": [str(item)[:500] for item in (raw.get("missing_evidence") or [])[:8]],
            "alternative_explanations": [str(item)[:500] for item in (raw.get("alternative_explanations") or [])[:8]],
            "confidence": confidence,
            "revision": revision,
            "revision_history": history,
            "created_at_step": (previous or {}).get("created_at_step"),
            "updated_at_step": raw.get("updated_at_step"),
            "history": history,
        }
    state["hypotheses"] = list(by_id.values())[:MAX_HYPOTHESES]
    competition: dict[str, list[dict]] = {}
    status_priority = {"supported": 0, "investigating": 1, "proposed": 2, "unresolved": 3, "weakened": 4, "refuted": 5}
    for item in state["hypotheses"]:
        competition.setdefault(str(item.get("competition_group") or "default"), []).append(item)
    state["hypothesis_competition"] = {
        group: [
            {"hypothesis_id": item.get("hypothesis_id"), "status": item.get("status"),
             "confidence": item.get("confidence"), "rank": rank + 1}
            for rank, item in enumerate(sorted(items, key=lambda value: (
                status_priority.get(str(value.get("status")), 9),
                -float(value.get("confidence") or 0), str(value.get("hypothesis_id"))
            )))
        ] for group, items in competition.items()
    }
    state["evidence_gaps"] = analyze_evidence_gaps(state)
    state.setdefault("epistemic_state", {})["active_hypotheses"] = [
        item["hypothesis_id"] for item in state["hypotheses"]
        if item.get("status") in {"proposed", "investigating", "supported"}
    ]
    state["epistemic_state"]["rejected_hypotheses"] = [
        item["hypothesis_id"] for item in state["hypotheses"]
        if item.get("status") in {"refuted", "weakened"}
    ]
    state["epistemic_state"]["evidence_gaps"] = [item.get("gap_id") for item in state["evidence_gaps"]]
    state["epistemic_state"]["alternative_explanations"] = list({
        explanation
        for item in state["hypotheses"]
        for explanation in item.get("alternative_explanations", [])
    })[:20]
    build_contradiction_matrix(state)
    memory = state.setdefault("case_memory", {})
    memory["case_id"] = state.get("case_id")
    memory["rejected_hypotheses"] = list({
        *memory.get("rejected_hypotheses", []),
        *(item["hypothesis_id"] for item in state["hypotheses"] if item.get("status") in {"weakened", "refuted"}),
    })[:MAX_HYPOTHESES]
    memory["known_benign_patterns"] = list({
        *memory.get("known_benign_patterns", []),
        *(explanation for item in state["hypotheses"] for explanation in item.get("alternative_explanations", [])),
    })[:20]
    memory["relevant_evidence_ids"] = list({
        *memory.get("relevant_evidence_ids", []),
        *(evidence_id for item in state["hypotheses"]
          for evidence_id in [*(item.get("supporting_evidence_ids") or []), *(item.get("contradicting_evidence_ids") or []), *(item.get("neutral_evidence_ids") or [])]),
    })[:MAX_OBSERVED_EVIDENCE]
    state["next_action"] = select_next_action(state)
    state["epistemic_state"]["next_action"] = state["next_action"]


def record_tool_observation(state: dict, tool_name: str, evidence_ids: list[str],
                            result_count: int | None = None, step_number: int | None = None,
                            result_fingerprint: str | None = None, result_data: dict | None = None,
                            result_bytes: int | None = None) -> dict:
    previous_evidence = set(state.get("collected_evidence_ids") or [])
    previous_gaps = {str(item.get("gap_id")) for item in (state.get("evidence_gaps") or [])
                     if item.get("status", "open") == "open"}
    observed = list(state.get("collected_evidence_ids") or [])
    for evidence_id in evidence_ids:
        if evidence_id not in observed:
            observed.append(evidence_id)
    state["collected_evidence_ids"] = observed[:MAX_OBSERVED_EVIDENCE]
    state["epistemic_state"]["observed_evidence_ids"] = state["collected_evidence_ids"]
    state["epistemic_state"]["remaining_budget"]["tool_calls"] = state.get("remaining_tool_budget")
    accounting = state.setdefault("cost_accounting", {})
    accounting["tool_calls"] = int(accounting.get("tool_calls") or 0) + 1
    accounting["tool_result_bytes"] = int(accounting.get("tool_result_bytes") or 0) + int(result_bytes or 0)
    if tool_name in {"search_external_events", "get_external_source_status"}:
        accounting["external_source_calls"] = int(accounting.get("external_source_calls") or 0) + 1
    # Provider health is a precondition check, not completion of an
    # investigation objective.  Keep it observable without consuming a plan step.
    step = None if tool_name == "get_external_source_status" else _plan_step_for_tool(state, tool_name)
    action = select_next_action(state)
    if step is not None:
        step["status"] = "completed"
        step["status_reason"] = f"tool_observed:{tool_name}"
        step["completed_at_step"] = step_number
        if step.get("step_id") not in state.get("completed_steps", []):
            state.setdefault("completed_steps", []).append(step.get("step_id"))
    for evidence_id in evidence_ids:
        record_provenance(
            state, "evidence", evidence_id, "tool_observation", tool_name,
            "observed_by", step_id=step.get("step_id") if step else None,
            metadata={"result_count": result_count},
        )
    state.setdefault("case_memory", {})["relevant_evidence_ids"] = list({
        *(state.get("case_memory", {}).get("relevant_evidence_ids") or []),
        *state.get("collected_evidence_ids", []),
    })[:MAX_OBSERVED_EVIDENCE]
    state.setdefault("action_history", []).append({
        "action": tool_name,
        "status": "empty" if result_count == 0 else "completed",
        "result_count": result_count,
        "evidence_count": len(evidence_ids),
        "result_fingerprint": result_fingerprint,
        "limitations": ["tool returned no evidence"] if result_count == 0 else [],
        "selected_before": action,
        "at_step": step_number,
        "at": _utc_now(),
    })
    state["action_history"] = state["action_history"][-MAX_ACTION_HISTORY:]
    state["evidence_gaps"] = analyze_evidence_gaps(state)
    new_evidence = sorted(set(evidence_ids) - previous_evidence)
    new_gaps = {str(item.get("gap_id")) for item in (state.get("evidence_gaps") or [])
                if item.get("status", "open") == "open"}
    resolved_gaps = sorted(previous_gaps - new_gaps)
    mark_progress(state, signal="NEW_EVIDENCE" if new_evidence else "PLAN_STEP_COMPLETED" if step else "NO_NEW_EVIDENCE",
                  evidence_ids=new_evidence, gap_ids=resolved_gaps, useful=bool(new_evidence or step))
    if isinstance(result_data, dict):
        for event_item in (result_data.get("events") or [])[:MAX_OBSERVED_EVIDENCE]:
            if not isinstance(event_item, dict):
                continue
            evidence_id = event_item.get("event_id") or event_item.get("evidence_id")
            if evidence_id:
                record_evidence_quality(
                    state, str(evidence_id),
                    integrity_status="verified" if event_item.get("event_origin") in {"local", "external"} else "unknown",
                    parser_quality=event_item.get("parser_confidence"),
                    timestamp_quality=event_item.get("timestamp_confidence"),
                    directness="direct", source_type=str(event_item.get("source_type") or "unknown"),
                    completeness=1.0 if event_item.get("raw_log") is not None else 0.5,
                    corroborated=str(evidence_id) in previous_evidence,
                    quality_flags=list(event_item.get("timestamp_assumptions") or []),
                )
    build_contradiction_matrix(state)
    state["next_action"] = select_next_action(state)
    state["epistemic_state"]["next_action"] = state["next_action"]
    return state["next_action"]


def record_result_provenance(state: dict, result: Any, tool_name: str,
                             step_id: str | None = None) -> None:
    """Project safe IDs from a tool result into the operational provenance graph."""
    if not isinstance(result, dict):
        return
    for item in result.get("events") or []:
        if not isinstance(item, dict):
            continue
        event_id = item.get("event_id") or item.get("evidence_id")
        if event_id:
            record_provenance(state, "evidence", str(event_id), "event", str(event_id),
                              "projects_to", step_id=step_id, metadata={"tool": tool_name})
    for item in result.get("correlations") or []:
        if not isinstance(item, dict) or not item.get("correlation_id"):
            continue
        correlation_id = str(item["correlation_id"])
        for key in ("event_id", "related_event_id"):
            if item.get(key):
                record_provenance(state, "event", str(item[key]), "correlation", correlation_id,
                                  "linked_by", step_id=step_id, metadata={"tool": tool_name})
    for item in result.get("findings") or []:
        if not isinstance(item, dict) or not item.get("finding_id"):
            continue
        finding_id = str(item["finding_id"])
        for evidence_id in item.get("evidence_ids") or []:
            record_provenance(state, "finding", finding_id, "evidence", str(evidence_id),
                              "supported_by", step_id=step_id, metadata={"tool": tool_name})


def update_from_draft(state: dict, draft: dict, step_number: int | None = None) -> dict:
    if isinstance(draft, dict) and isinstance(draft.get("plan_updates"), list):
        revise_plan(state, draft.get("plan_updates"), str(draft.get("plan_revision_reason") or "model proposed bounded plan update"))
    merge_hypotheses(state, draft.get("hypotheses") if isinstance(draft, dict) else None)
    for hypothesis in state.get("hypotheses", []):
        hypothesis_id = hypothesis.get("hypothesis_id")
        for evidence_id in [*(hypothesis.get("supporting_evidence_ids") or []), *(hypothesis.get("contradicting_evidence_ids") or [])]:
            record_provenance(state, "hypothesis", str(hypothesis_id), "evidence", str(evidence_id),
                              "supported_by" if evidence_id in (hypothesis.get("supporting_evidence_ids") or []) else "contradicted_by",
                              step_id=f"step-{step_number:03d}" if step_number is not None else None)
    if step_number is not None:
        for item in state.get("hypotheses", []):
            if item.get("updated_at_step") is None:
                item["updated_at_step"] = step_number
                if item.get("created_at_step") is None:
                    item["created_at_step"] = step_number
    supplied_gaps = draft.get("evidence_gaps") if isinstance(draft, dict) else None
    if isinstance(supplied_gaps, list):
        for raw in supplied_gaps[:MAX_GAPS]:
            if not isinstance(raw, dict) or not raw.get("description"):
                continue
            item = {
                "gap_id": str(raw.get("gap_id") or f"gap-model-{len(state['evidence_gaps']) + 1}"),
                "hypothesis_id": raw.get("hypothesis_id"),
                "description": str(raw["description"])[:500],
                "priority": str(raw.get("priority") or "medium").lower(),
                "candidate_tools": [str(tool) for tool in (raw.get("candidate_tools") or ["search_events"])[:4]],
                "status": "open",
                "plan_step_id": raw.get("plan_step_id"),
            }
            if item["gap_id"] not in {gap.get("gap_id") for gap in state["evidence_gaps"]}:
                state["evidence_gaps"].append(item)
    alternatives = draft.get("alternative_explanations") if isinstance(draft, dict) else None
    if isinstance(alternatives, list):
        state["epistemic_state"]["alternative_explanations"] = [
            str(item)[:500] for item in alternatives[:10] if str(item).strip()
        ]
    state["evidence_gaps"] = analyze_evidence_gaps(state)
    memory = state.setdefault("case_memory", {})
    memory["unresolved_questions"] = [
        gap.get("description") for gap in state["evidence_gaps"] if gap.get("status", "open") == "open"
    ][:MAX_GAPS]
    memory["resolved_questions"] = [
        item.get("objective") for item in (state.get("plan", {}).get("steps") or [])
        if item.get("status") == "completed"
    ][:20]
    state["next_action"] = select_next_action(state)
    state["epistemic_state"]["next_action"] = state["next_action"]
    return state


def record_repair(state: dict, failure_reasons: list[dict], action: str, result: str) -> int:
    repair = state.setdefault("repair_state", {"attempts": [], "max_attempts": 2})
    attempts = repair.setdefault("attempts", [])
    attempt_number = len(attempts) + 1
    attempts.append({
        "repair_attempt": attempt_number,
        "failure_reasons": failure_reasons[:20],
        "action_taken": action,
        "result": result,
        "at": _utc_now(),
    })
    repair["attempts"] = attempts[-3:]
    state.setdefault("cost_accounting", {})["repair_count"] = len(attempts)
    return attempt_number


def set_stop(state: dict, reason: str, detail: str | None = None) -> None:
    if reason not in STOP_REASONS:
        reason = "PROVIDER_FAILURE"
    state["stop_state"] = {"reason": reason, "detail": detail, "decided_at": _utc_now()}
    state["next_action"] = None
    state["epistemic_state"]["next_action"] = None


def public_state_summary(state: dict) -> dict:
    """Return bounded operational state; never include model messages/reasoning."""
    plan = deepcopy(state.get("plan") or {})
    plan.pop("revision_history", None)
    summary = {
        "state_schema_version": state.get("state_schema_version", STATE_SCHEMA_VERSION),
        "current_state": lifecycle_state(state),
        "lifecycle": deepcopy(state.get("lifecycle") or {}),
        "plan": plan,
        "hypotheses": deepcopy(state.get("hypotheses") or [])[:MAX_HYPOTHESES],
        "hypothesis_competition": deepcopy(state.get("hypothesis_competition") or {}),
        "evidence_gaps": deepcopy(state.get("evidence_gaps") or [])[:MAX_GAPS],
        "epistemic_state": deepcopy(state.get("epistemic_state") or {}),
        "repair_state": {
            "attempt_count": len((state.get("repair_state") or {}).get("attempts") or []),
            "max_attempts": (state.get("repair_state") or {}).get("max_attempts", 2),
            "last_attempt": ((state.get("repair_state") or {}).get("attempts") or [])[-1:] or None,
        },
        "case_memory": {
            **deepcopy(state.get("case_memory") or {}),
            "relevant_evidence_ids": list((state.get("case_memory") or {}).get("relevant_evidence_ids") or [])[:MAX_OBSERVED_EVIDENCE],
        },
        "provenance": deepcopy(state.get("provenance") or [])[-MAX_PROVENANCE:],
        "stop_state": deepcopy(state.get("stop_state") or {}),
        "verification_summary": deepcopy(state.get("verification_summary") or {}),
        "next_action": deepcopy(state.get("next_action")),
        "candidate_actions": deepcopy(state.get("candidate_actions") or [])[:MAX_CANDIDATE_ACTIONS],
        "action_ranking": deepcopy(state.get("action_ranking") or {}),
        "evidence_quality": deepcopy(state.get("evidence_quality") or {}),
        "contradiction_matrix": deepcopy(state.get("contradiction_matrix") or {}),
        "cost_accounting": deepcopy(state.get("cost_accounting") or {}),
        "progress": deepcopy(state.get("progress") or {}),
        "completed_steps": list(state.get("completed_steps") or [])[-20:],
        "collected_evidence_count": len(state.get("collected_evidence_ids") or []),
        "remaining_tool_budget": state.get("remaining_tool_budget"),
    }
    return summary
