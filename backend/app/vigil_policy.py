"""Deterministic VIGIL state and action policy.

The LLM may propose a plan, tool call, hypothesis update, or stop reason, but
this module authorizes the operation. It contains no network or database calls.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


STATE_MACHINE_VERSION = "vigil-state-machine-v1"
TRANSITION_VERSION = "v1"

INVESTIGATION_STATES = {
    "INITIALIZED",
    "PLANNING",
    "INVESTIGATING",
    "EVIDENCE_REVIEW",
    "VERIFYING",
    "REPAIRING",
    "COMPLETED",
    "ABSTAINED",
    "PAUSED",
    "CANCELLED",
    "FAILED",
}

TERMINAL_STATES = {"COMPLETED", "ABSTAINED", "CANCELLED", "FAILED"}

VALID_TRANSITIONS: dict[str, set[str]] = {
    "INITIALIZED": {"PLANNING", "PAUSED", "CANCELLED", "FAILED"},
    "PLANNING": {"INVESTIGATING", "PAUSED", "CANCELLED", "FAILED"},
    "INVESTIGATING": {"EVIDENCE_REVIEW", "PAUSED", "CANCELLED", "FAILED"},
    "EVIDENCE_REVIEW": {"VERIFYING", "INVESTIGATING", "PAUSED", "CANCELLED", "FAILED"},
    "VERIFYING": {"REPAIRING", "COMPLETED", "ABSTAINED", "PAUSED", "CANCELLED", "FAILED"},
    "REPAIRING": {"INVESTIGATING", "VERIFYING", "ABSTAINED", "PAUSED", "CANCELLED", "FAILED"},
    "PAUSED": {"INVESTIGATING", "CANCELLED", "FAILED"},
    "COMPLETED": set(),
    "ABSTAINED": set(),
    "CANCELLED": set(),
    "FAILED": set(),
}

@dataclass(frozen=True)
class PolicyDecision:
    allowed: bool
    reason_code: str
    detail: str = ""

class InvalidTransition(ValueError):
    """Raised when a run tries to enter an illegal lifecycle state."""

def lifecycle_state(state: dict[str, Any]) -> str:
    lifecycle = state.get("lifecycle") or {}
    return str(lifecycle.get("current_state") or state.get("current_state") or "INITIALIZED")

def transition_allowed(current: str, target: str, *, replay: bool = False) -> bool:
    if current not in INVESTIGATION_STATES or target not in INVESTIGATION_STATES:
        return False
    if replay and current in TERMINAL_STATES and target == "INITIALIZED":
        return True
    return target in VALID_TRANSITIONS.get(current, set())

def transition_state(state: dict[str, Any], target: str, reason: str,
                     *, replay: bool = False, at: str | None = None) -> dict[str, Any]:
    current = lifecycle_state(state)
    target = str(target).upper()
    if not transition_allowed(current, target, replay=replay):
        raise InvalidTransition(f"invalid VIGIL transition {current} -> {target}")
    timestamp = at or datetime.now(timezone.utc).isoformat()
    lifecycle = state.setdefault("lifecycle", {})
    history = lifecycle.setdefault("transition_history", [])
    item = {
        "previous_state": current,
        "current_state": target,
        "transition_reason": str(reason)[:200],
        "transition_timestamp": timestamp,
        "transition_version": TRANSITION_VERSION,
    }
    history.append(item)
    lifecycle["transition_history"] = history[-100:]
    lifecycle.update(item)
    lifecycle["state_machine_version"] = STATE_MACHINE_VERSION
    state["current_state"] = target
    return state

def ensure_lifecycle(state: dict[str, Any]) -> dict[str, Any]:
    lifecycle = state.setdefault("lifecycle", {})
    current = lifecycle.get("current_state") or state.get("current_state") or "INITIALIZED"
    if current not in INVESTIGATION_STATES:
        current = "INITIALIZED"
    lifecycle.setdefault("state_machine_version", STATE_MACHINE_VERSION)
    lifecycle.setdefault("current_state", current)
    lifecycle.setdefault("previous_state", None)
    lifecycle.setdefault("transition_reason", "STATE_RESTORED")
    lifecycle.setdefault("transition_timestamp", datetime.now(timezone.utc).isoformat())
    lifecycle.setdefault("transition_version", TRANSITION_VERSION)
    lifecycle.setdefault("transition_history", [])
    state["current_state"] = lifecycle["current_state"]
    return state

class InvestigationPolicy:
    """Deterministic policy authorization for VIGIL operations."""

    def __init__(self, *, allowed_tools: set[str], max_tool_calls: int,
                 max_revisions: int = 3, max_repairs: int = 2,
                 max_same_tool_repetition: int = 2):
        self.allowed_tools = set(allowed_tools)
        self.max_tool_calls = max(0, int(max_tool_calls))
        self.max_revisions = max(0, int(max_revisions))
        self.max_repairs = max(0, int(max_repairs))
        self.max_same_tool_repetition = max(1, int(max_same_tool_repetition))

    def can_transition(self, state: dict[str, Any], target: str, *, replay: bool = False) -> PolicyDecision:
        current = lifecycle_state(state)
        if transition_allowed(current, target, replay=replay):
            return PolicyDecision(True, "TRANSITION_ALLOWED")
        return PolicyDecision(False, "INVALID_STATE_TRANSITION", f"{current} -> {target}")

    def can_call_tool(self, state: dict[str, Any], tool_name: str,
                      repeated_count: int = 0, *, precondition: bool = False) -> PolicyDecision:
        tool_name = str(tool_name)
        if tool_name not in self.allowed_tools:
            return PolicyDecision(False, "TOOL_NOT_ALLOWLISTED", tool_name)
        if int(state.get("tool_call_count") or 0) >= self.max_tool_calls:
            return PolicyDecision(False, "TOOL_BUDGET_EXCEEDED")
        if repeated_count >= self.max_same_tool_repetition:
            return PolicyDecision(False, "TOOL_REPETITION_EXCEEDED")
        if lifecycle_state(state) in TERMINAL_STATES:
            return PolicyDecision(False, "RUN_TERMINAL")
        if not precondition and lifecycle_state(state) not in {"PLANNING", "INVESTIGATING", "EVIDENCE_REVIEW", "REPAIRING"}:
            return PolicyDecision(False, "TOOL_STATE_NOT_ALLOWED", lifecycle_state(state))
        return PolicyDecision(True, "TOOL_ALLOWED")

    def can_repair(self, state: dict[str, Any]) -> PolicyDecision:
        count = len((state.get("repair_state") or {}).get("attempts") or [])
        maximum = int((state.get("repair_state") or {}).get("max_attempts", self.max_repairs))
        if count >= min(maximum, self.max_repairs):
            return PolicyDecision(False, "REPAIR_BUDGET_EXCEEDED")
        return PolicyDecision(True, "REPAIR_ALLOWED")

    def can_replan(self, state: dict[str, Any]) -> PolicyDecision:
        plan = state.get("plan") or {}
        revision = int(plan.get("revision") or 0)
        maximum = min(int(plan.get("max_revisions") or self.max_revisions), self.max_revisions)
        if revision >= maximum:
            return PolicyDecision(False, "PLAN_REVISION_BUDGET_EXCEEDED")
        return PolicyDecision(True, "PLAN_REVISION_ALLOWED")

    def can_update_hypothesis(self, state: dict[str, Any], status: str,
                              evidence_ids: list[str]) -> PolicyDecision:
        if lifecycle_state(state) in TERMINAL_STATES:
            return PolicyDecision(False, "RUN_TERMINAL")
        if str(status).lower() not in {"proposed", "investigating", "supported", "weakened", "refuted", "unresolved"}:
            return PolicyDecision(False, "HYPOTHESIS_STATUS_INVALID")
        if str(status).lower() in {"supported", "weakened", "refuted"} and not evidence_ids:
            return PolicyDecision(False, "HYPOTHESIS_EVIDENCE_REQUIRED")
        return PolicyDecision(True, "HYPOTHESIS_UPDATE_ALLOWED")

    def can_stop(self, state: dict[str, Any], reason: str) -> PolicyDecision:
        if lifecycle_state(state) in TERMINAL_STATES:
            return PolicyDecision(False, "RUN_ALREADY_TERMINAL")
        if not str(reason):
            return PolicyDecision(False, "STOP_REASON_REQUIRED")
        return PolicyDecision(True, "STOP_ALLOWED")

def score_action(*, gap_priority: str = "medium", hypothesis_relevance: float = 0.5,
                 expected_evidence_value: float = 0.5, source_diversity_bonus: float = 0.0,
                 novelty_bonus: float = 0.0, estimated_cost: float = 1.0,
                 repeat_penalty: float = 0.0, remaining_budget: int = 1) -> float:
    priority = {"critical": 1.0, "high": 0.8, "medium": 0.6, "low": 0.4}.get(str(gap_priority).lower(), 0.4)
    denominator = max(0.25, float(estimated_cost)) * max(0.25, 1.0 + float(repeat_penalty))
    budget_factor = min(1.0, max(0.1, float(remaining_budget) / 10.0))
    raw = priority * max(0.0, min(1.0, hypothesis_relevance)) * max(0.0, min(1.0, expected_evidence_value))
    raw += max(0.0, min(0.3, source_diversity_bonus)) + max(0.0, min(0.3, novelty_bonus))
    return round(max(0.0, min(1.0, raw * budget_factor / denominator)), 4)

def rank_actions(candidates: list[dict[str, Any]], *, remaining_budget: int) -> list[dict[str, Any]]:
    ranked: list[dict[str, Any]] = []
    for candidate in candidates:
        item = dict(candidate)
        item["score"] = score_action(
            gap_priority=item.get("gap_priority", "medium"),
            hypothesis_relevance=float(item.get("hypothesis_relevance", 0.5)),
            expected_evidence_value=float(item.get("expected_evidence_value", 0.5)),
            source_diversity_bonus=float(item.get("source_diversity_bonus", 0.0)),
            novelty_bonus=float(item.get("novelty_bonus", 0.0)),
            estimated_cost=float(item.get("estimated_cost", 1.0)),
            repeat_penalty=float(item.get("repeat_penalty", 0.0)),
            remaining_budget=remaining_budget,
        )
        item["estimated_cost"] = max(1, int(item.get("estimated_cost", 1)))
        item.setdefault("reason_codes", [])
        ranked.append(item)
    ranked.sort(key=lambda item: (-float(item["score"]), str(item.get("candidate_action", ""))))
    return ranked
