import json
from pathlib import Path

from evals.phase2_metrics import evaluate_dataset
from evals.run_adversarial_eval import run as run_adversarial


def test_phase2_metrics_cover_golden_cases_and_gate_ablation():
    root = Path(__file__).parents[1]
    report = evaluate_dataset(json.loads((root / "evals" / "phase2_golden_cases.json").read_text(encoding="utf-8")))
    assert report["summary"]["pass_rate"] == 1.0
    assert report["summary"]["unsupported_claim_rate_gate_on"] == 0.0
    assert report["summary"]["unsupported_claim_rate_gate_off"] > 0.0
    assert report["summary"]["forbidden_tool_violation_rate"] == 0.0


def test_adversarial_smoke_suite_is_policy_only_and_green():
    root = Path(__file__).parents[1]
    report = run_adversarial(root / "evals" / "adversarial_cases.json")
    assert report["pass_rate"] == 1.0
    assert "not an independent red-team" in report["scope"]
