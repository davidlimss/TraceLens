"""Offline evaluation for VIGIL operational state (no provider/network)."""
from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.vigil import ALLOWED_PLAN_TOOLS, initial_vigil_state, merge_hypotheses, record_tool_observation, set_stop


def run(dataset: Path) -> dict:
    cases = json.loads(dataset.read_text(encoding="utf-8"))
    results = []
    for spec in cases:
        state = initial_vigil_state(uuid.uuid4(), spec["question"], 8, max_repairs=2)
        hypothesis = dict(spec["hypothesis"])
        evidence = [str(uuid.UUID(value)) for value in hypothesis.get("supporting_evidence_ids", [])]
        evidence.extend(str(uuid.UUID(value)) for value in hypothesis.get("contradicting_evidence_ids", []))
        merge_hypotheses(state, [hypothesis], observed_ids=set(evidence))
        first_action = state.get("next_action", {}).get("reason_code")
        record_tool_observation(state, spec["observed_tool"], evidence, 0, 1)
        if spec.get("final_hypothesis_status"):
            final_hypothesis = {**hypothesis, "status": spec["final_hypothesis_status"]}
            merge_hypotheses(state, [final_hypothesis], observed_ids=set(evidence))
        set_stop(state, spec["expected_stop"], "offline evaluation decision")
        expected_status = spec.get("expected_hypothesis_status")
        hypothesis_status_ok = not expected_status or state["hypotheses"][0]["status"] == expected_status
        plan_tools = {tool for step in state["plan"]["steps"] for tool in step.get("suggested_tools", [])}
        plan_policy_ok = plan_tools.issubset(ALLOWED_PLAN_TOOLS)
        passed = (
            first_action == spec["expected_first_action"]
            and state["stop_state"]["reason"] == spec["expected_stop"]
            and state["state_schema_version"] == "vigil-state-v2"
            and hypothesis_status_ok
            and plan_policy_ok
        )
        results.append({"id": spec["id"], "passed": passed, "first_action": first_action,
                        "stop_reason": state["stop_state"]["reason"],
                        "hypothesis_count": len(state["hypotheses"]),
                        "gap_count": len(state["evidence_gaps"]),
                        "hypothesis_status": state["hypotheses"][0]["status"],
                        "plan_policy_ok": plan_policy_ok})
    passed = sum(item["passed"] for item in results)
    return {"mode": "offline-vigil", "passed": passed, "total": len(results),
            "pass_rate": passed / len(results) if results else 1.0, "cases": results}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, default=Path(__file__).with_name("vigil_cases.json"))
    parser.add_argument("--min-pass-rate", type=float, default=1.0)
    args = parser.parse_args()
    report = run(args.dataset)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["pass_rate"] >= args.min_pass_rate else 1


if __name__ == "__main__":
    raise SystemExit(main())
