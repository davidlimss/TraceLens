"""Run the provider-independent VIGIL Phase 2 evaluation harness."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from evals.phase2_metrics import evaluate_dataset


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, default=Path(__file__).with_name("phase2_golden_cases.json"))
    parser.add_argument("--output", type=Path, default=Path("phase2-eval-results.json"))
    parser.add_argument("--min-pass-rate", type=float, default=1.0)
    args = parser.parse_args()
    report = evaluate_dataset(json.loads(args.dataset.read_text(encoding="utf-8")))
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["summary"]["pass_rate"] >= args.min_pass_rate else 1


if __name__ == "__main__":
    raise SystemExit(main())
