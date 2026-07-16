"""TraceLens evaluation harness.

Offline (no token/network): python evals/run_eval.py
Live case: python evals/run_eval.py --live-case <UUID>
Exit code is non-zero when the configured quality gate fails.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.claim_verifier import INSUFFICIENT_EVIDENCE, verify_claims
from app.config import get_settings
from app.database import SessionLocal
from app.llm_gateway import LLMGateway
from app.models import Base, Case, Event, EvidenceFile

FORBIDDEN_OVERCLAIMS = ("pasti diretas", "pasti penyerang", "confirmed compromise")


def add_event(db: Session, case: Case, evidence: EvidenceFile, spec: dict, line: int) -> Event:
    event = Event(case_id=case.case_id, evidence_file_id=evidence.evidence_file_id,
                  timestamp_original=f"2026-01-01T00:00:{line:02d}Z", timestamp_normalized=None,
                  source_type="eval", source_name="golden", event_category="authentication",
                  event_action=spec.get("action", "message"), event_outcome=spec.get("outcome"),
                  severity=spec.get("severity", "info"), source_ip=spec.get("source_ip"),
                  username=spec.get("username", "admin"), raw_log=json.dumps(spec), raw_line_number=line,
                  parser_name="eval", parser_confidence=1.0, tags=[], timestamp_confidence=1.0,
                  timestamp_assumptions=[])
    db.add(event); db.flush(); return event


def materialize_claims(draft: dict, event_ids: list[uuid.UUID]) -> dict:
    result = json.loads(json.dumps(draft))
    for claim in result.get("claims", []):
        refs = claim.pop("evidence_refs", [])
        claim["supporting_evidence_ids"] = [str(event_ids[index]) if 0 <= index < len(event_ids)
                                             else str(uuid.uuid4()) for index in refs]
    return result


def run_offline(dataset: Path) -> dict:
    engine = create_engine("sqlite+pysqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    results = []
    with Session(engine) as db:
        for spec in json.loads(dataset.read_text(encoding="utf-8")):
            case = Case(name=spec["id"]); db.add(case); db.flush()
            evidence = EvidenceFile(case_id=case.case_id, original_filename="golden.jsonl",
                                    storage_path=f"eval-only-{case.case_id}", sha256="0"*64, size_bytes=1,
                                    detected_format="application_json", status="parsed")
            db.add(evidence); db.flush()
            events = [add_event(db, case, evidence, event, index+1) for index,event in enumerate(spec["events"])]
            response = verify_claims(db, case.case_id, materialize_claims(spec["draft"], [e.event_id for e in events]))
            grounded = all(str(claim.evidence_id) in response.answer for claim in response.claims)
            refusal = response.answer == INSUFFICIENT_EVIDENCE
            passed = (len(response.claims) == spec["expected_claims"] and
                      refusal == spec["expected_refusal"] and grounded)
            results.append({"id":spec["id"],"passed":passed,"claims":len(response.claims),
                            "refusal":refusal,"grounded":grounded})
    passed = sum(item["passed"] for item in results)
    return {"mode":"offline","passed":passed,"total":len(results),"pass_rate":passed/len(results),"cases":results}


def run_live(case_id: uuid.UUID) -> dict:
    questions = ["Apa yang terjadi pada case ini?", "Apakah ada login gagal berulang?",
                 "Apakah bukti cukup untuk menyatakan sistem telah dikompromikan?"]
    settings = get_settings()
    if not settings.github_models_token:
        raise SystemExit("GITHUB_MODELS_TOKEN belum dikonfigurasi untuk live eval")
    results=[]
    with SessionLocal() as db:
        for question in questions:
            started=time.perf_counter(); response,metrics=LLMGateway(settings).chat(db,case_id,question)
            latency_ms=round((time.perf_counter()-started)*1000,2)
            grounded=all(str(claim.evidence_id) in response.answer for claim in response.claims)
            safe=not any(term in response.answer.lower() for term in FORBIDDEN_OVERCLAIMS)
            results.append({"question":question,"passed":grounded and safe,"claims":len(response.claims),
                            "grounded":grounded,"safe":safe,"latency_ms":latency_ms,"agent_metrics":metrics})
    passed=sum(item["passed"] for item in results)
    return {"mode":"live","case_id":str(case_id),"passed":passed,"total":len(results),
            "pass_rate":passed/len(results),"cases":results}


def main() -> int:
    parser=argparse.ArgumentParser(); parser.add_argument("--dataset",type=Path,default=Path(__file__).with_name("golden_cases.json")); parser.add_argument("--live-case",type=uuid.UUID); parser.add_argument("--output",type=Path,default=Path("eval-results.json")); parser.add_argument("--min-pass-rate",type=float,default=1.0); args=parser.parse_args()
    report=run_live(args.live_case) if args.live_case else run_offline(args.dataset)
    args.output.write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding="utf-8")
    print(json.dumps(report,indent=2,ensure_ascii=False))
    return 0 if report["pass_rate"] >= args.min_pass_rate else 1


if __name__ == "__main__":
    raise SystemExit(main())
