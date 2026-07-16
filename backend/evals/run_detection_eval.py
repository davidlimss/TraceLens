"""Deterministic detection benchmark with precision/recall/F1 quality gates."""
from __future__ import annotations
import argparse
import json
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.engine import build_correlations, detect_auth_findings, detect_extended_findings
from app.models import Event


def materialize(case_id, specs):
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    result=[]
    for index, spec in enumerate(specs):
        result.append(Event(event_id=uuid.uuid4(), case_id=case_id, evidence_file_id=uuid.uuid4(),
            timestamp_original=None, timestamp_normalized=base+timedelta(seconds=index*30), timezone="UTC",
            source_type="eval", source_name="golden", event_category=spec.get("category","authentication"),
            event_action=spec.get("action","message"), event_outcome=spec.get("outcome"), severity="info",
            username=spec.get("user"), source_ip=spec.get("ip"), command_line=spec.get("command_line"),
            url_path=spec.get("url_path"), raw_log=json.dumps(spec), raw_line_number=index+1,
            parser_name="eval", parser_confidence=1.0, tags=[], timestamp_confidence=1.0,
            timestamp_assumptions=[]))
    return result


def run(dataset: Path):
    rows=[]; tp=fp=fn=0
    for case in json.loads(dataset.read_text(encoding="utf-8")):
        events=materialize(uuid.uuid4(),case["events"])
        correlations=build_correlations(events,10)
        findings=detect_auth_findings(events,correlations,threshold=5,window_minutes=10)
        findings+=detect_extended_findings(events,threshold=5,window_minutes=10)
        actual={item.finding_type for item in findings}; expected=set(case["expected"])
        case_tp=len(actual&expected); case_fp=len(actual-expected); case_fn=len(expected-actual)
        tp+=case_tp; fp+=case_fp; fn+=case_fn
        rows.append({"id":case["id"],"expected":sorted(expected),"actual":sorted(actual),
                     "passed":case_fp==0 and case_fn==0})
    precision=tp/(tp+fp) if tp+fp else 1.0
    recall=tp/(tp+fn) if tp+fn else 1.0
    f1=2*precision*recall/(precision+recall) if precision+recall else 0.0
    return {"true_positive":tp,"false_positive":fp,"false_negative":fn,
            "precision":round(precision,4),"recall":round(recall,4),"f1":round(f1,4),"cases":rows}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--dataset",type=Path,default=Path(__file__).with_name("detection_cases.json"))
    parser.add_argument("--output",type=Path,default=Path("detection-eval-results.json"))
    parser.add_argument("--min-precision",type=float,default=.85)
    parser.add_argument("--min-recall",type=float,default=.80)
    args=parser.parse_args(); report=run(args.dataset)
    args.output.write_text(json.dumps(report,indent=2),encoding="utf-8")
    print(json.dumps(report,indent=2))
    return 0 if report["precision"]>=args.min_precision and report["recall"]>=args.min_recall else 1


if __name__ == "__main__":
    raise SystemExit(main())
