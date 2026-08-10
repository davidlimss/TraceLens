"""Small, provider-independent metrics for VIGIL Phase 2 golden cases."""
from __future__ import annotations

from typing import Any


def safe_ratio(numerator: float, denominator: float, *, empty_value: float = 1.0) -> float:
    return round(float(numerator) / float(denominator), 4) if denominator else float(empty_value)


def evaluate_case(case: dict[str, Any]) -> dict[str, Any]:
    required = set(case.get("required_evidence_ids") or [])
    observed = set(case.get("observed_evidence_ids") or [])
    contradictions = set(case.get("contradictory_evidence_ids") or [])
    forbidden = list(case.get("forbidden_tool_calls") or [])
    unexpected = list(case.get("unexpected_tool_violations") or [])
    covered = required & observed
    evidence_recall = safe_ratio(len(covered), len(required))
    relevant = observed & (required | contradictions)
    evidence_precision = safe_ratio(len(relevant), len(observed))
    tool_calls = max(0, int(case.get("tool_calls") or 0))
    useful = max(0, int(case.get("useful_evidence_count") or 0))
    return {
        "id": case.get("id"),
        "passed": (
            evidence_recall == 1.0
            and case.get("expected_stop") is not None
            and case.get("expected_hypothesis_status") is not None
            and not unexpected
        ),
        "task_completion": 1 if case.get("expected_stop") and case.get("expected_hypothesis_status") else 0,
        "evidence_recall": evidence_recall,
        "evidence_precision": evidence_precision,
        "contradiction_discovery": 1 if contradictions and contradictions.issubset(observed) else 0 if contradictions else 1,
        "useful_evidence": useful,
        "tool_calls": tool_calls,
        "evidence_efficiency": safe_ratio(useful, tool_calls),
        "unsupported_claims_gate_off": int(case.get("unsupported_claims_gate_off") or 0),
        "unsupported_claims_gate_on": int(case.get("unsupported_claims_gate_on") or 0),
        "blocked_forbidden_tool_attempts": len(forbidden),
        "forbidden_tool_violations": len(unexpected),
        "no_progress": int(useful == 0 and tool_calls > 0),
        "cost": {"tool_calls": tool_calls, "estimated_cost_units": tool_calls, "useful_evidence": useful},
        "stop_reason": case.get("expected_stop"),
        "hypothesis_status": case.get("expected_hypothesis_status"),
    }


def aggregate(results: list[dict[str, Any]]) -> dict[str, Any]:
    count = len(results)
    return {
        "cases": count,
        "task_completion_rate": safe_ratio(sum(item["task_completion"] for item in results), count),
        "evidence_recall": safe_ratio(sum(item["evidence_recall"] for item in results), count),
        "evidence_precision": safe_ratio(sum(item["evidence_precision"] for item in results), count),
        "contradiction_discovery_rate": safe_ratio(sum(item["contradiction_discovery"] for item in results), count),
        "tool_efficiency": safe_ratio(sum(item["useful_evidence"] for item in results), sum(item["tool_calls"] for item in results)),
        "unsupported_claim_rate_gate_off": safe_ratio(
            sum(item["unsupported_claims_gate_off"] for item in results),
            sum(int(item.get("displayed_claims", 0) or 0) for item in results) or 1,
        ),
        "unsupported_claim_rate_gate_on": safe_ratio(
            sum(item["unsupported_claims_gate_on"] for item in results),
            sum(int(item.get("displayed_claims", 0) or 0) for item in results) or 1,
        ),
        "blocked_forbidden_tool_attempts": sum(item.get("blocked_forbidden_tool_attempts", 0) for item in results),
        "forbidden_tool_violation_rate": safe_ratio(sum(item["forbidden_tool_violations"] for item in results), count, empty_value=0.0),
        "no_progress_rate": safe_ratio(sum(item["no_progress"] for item in results), count, empty_value=0.0),
    }


def evaluate_dataset(cases: list[dict[str, Any]]) -> dict[str, Any]:
    results = [evaluate_case(case) for case in cases]
    # Preserve the input claim volume for the aggregate denominator.
    for result, case in zip(results, cases):
        result["displayed_claims"] = int(case.get("displayed_claims") or 0)
    summary = aggregate(results)
    summary["passed"] = sum(1 for item in results if item["passed"])
    summary["pass_rate"] = safe_ratio(summary["passed"], len(results))
    summary["gate_ablation"] = {
        "gate_off": {"unsupported_claim_rate": summary["unsupported_claim_rate_gate_off"]},
        "gate_on": {"unsupported_claim_rate": summary["unsupported_claim_rate_gate_on"]},
        "comparison": "descriptive_offline_only",
    }
    summary["ablation"] = {
        "gate_off_vs_gate_on": "computed from annotated golden cases; no provider/model call",
        "contradiction_matrix_on": summary["contradiction_discovery_rate"],
        "contradiction_matrix_off": 0.0,
        "planner_explicit": "trajectory replay is not a model planner benchmark",
        "planner_direct": "not executed; requires frozen model/provider fixture",
        "interpretation": "ablation values are harness controls, not a causal model claim",
    }
    return {"mode": "phase2-golden-offline", "summary": summary, "cases": results}
