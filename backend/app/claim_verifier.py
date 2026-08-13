import re
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Event, ExternalEvidence
from app.schemas import AgentClaim, ChatResponse

INSUFFICIENT_EVIDENCE = "Belum cukup bukti untuk menjawab pertanyaan ini."
VALID_STATUSES = {"fact", "inference", "hypothesis"}
VERIFICATION_REASON_CODES = {
    "INVALID_CLAIM",
    "INVALID_STATUS",
    "INVALID_EVIDENCE_ID",
    "CROSS_CASE_EVIDENCE",
    "MISSING_SUPPORT",
    "INSUFFICIENT_EVIDENCE",
    "ENTITY_MISMATCH",
    "SEMANTIC_MISMATCH",
    "NUMERIC_OVERCLAIM",
    "UNSUPPORTED_SUCCESS_CLAIM",
    "UNSUPPORTED_FAILURE_CLAIM",
    "INVALID_INFERENCE",
    "MISSING_LIMITATION",
    "MISSING_REASONING_SUMMARY",
    "HYPOTHESIS_OVERCONFIDENCE",
    "CONTRADICTORY_EVIDENCE_IGNORED",
}
INTERPRETIVE_FACT_TERMS = {
    "penyerang", "diretas", "kompromi", "malware", "malicious", "mengambil alih",
    "exfiltration", "eksfiltrasi", "pencurian data", "insider threat",
}


def _sentences(text: str) -> list[str]:
    return [piece.strip() for piece in re.split(r"(?<=[.!?])\s+|[\r\n]+", text.strip()) if piece.strip()]


def _uuid_list(raw_claim: dict, key: str) -> list[uuid.UUID]:
    values = raw_claim.get(key) or []
    if isinstance(values, (str, uuid.UUID)):
        values = [values]
    parsed: list[uuid.UUID] = []
    for value in values:
        try:
            item = uuid.UUID(str(value))
            if item not in parsed:
                parsed.append(item)
        except (ValueError, TypeError, AttributeError):
            continue
    return parsed


def _entity_consistent(entities: dict, events: list[Event]) -> bool:
    columns = {"username": "username", "source_ip": "source_ip", "host": "host"}
    for key, expected in entities.items():
        if key in columns and expected and not any(str(getattr(event, columns[key]) or "") == str(expected) for event in events):
            return False
    return True


def _semantic_support(text: str, status: str, events: list[Event]) -> bool:
    lower = text.lower()
    if status == "fact" and any(term in lower for term in INTERPRETIVE_FACT_TERMS):
        return False
    if any(word in lower for word in ("berhasil", "successful", "success")) and not any(event.event_outcome == "success" for event in events):
        return False
    if any(word in lower for word in ("gagal", "failed", "failure")) and not any(event.event_outcome == "failure" for event in events):
        return False
    if "login" in lower and not any(event.event_action == "login" for event in events):
        return False
    stated_numbers = [int(value) for value in re.findall(
        r"\b(\d+)\s+(?:kali|times|events?|upaya|attempts?|login)", lower
    )]
    if stated_numbers and max(stated_numbers) > len(events):
        return False
    return True


def verify_claims_detailed(db: Session, case_id: uuid.UUID, draft: dict) -> tuple[ChatResponse, dict]:
    """Verify claims and return structured, operational rejection reasons.

    The draft is never trusted.  Only verified sentences are rebuilt into the
    answer.  Rejection diagnostics are safe metadata for the bounded repair
    loop; they do not include hidden model reasoning or raw secrets.
    """
    rejection_reasons: list[dict] = []

    def reject(index: int, code: str, detail: str) -> None:
        rejection_reasons.append({
            "claim_index": index,
            "reason_code": code if code in VERIFICATION_REASON_CODES else "INVALID_CLAIM",
            "detail": detail[:300],
        })

    if not isinstance(draft, dict):
        result = ChatResponse(answer=INSUFFICIENT_EVIDENCE, claims=[],
                              verification_summary={"verified_count": 0, "rejected_count": 0,
                                                     "rejection_reasons": []})
        return result, result.verification_summary
    verified: list[AgentClaim] = []
    for index, raw_claim in enumerate(draft.get("claims", [])):
        if not isinstance(raw_claim, dict):
            reject(index, "INVALID_CLAIM", "claim must be an object")
            continue
        if raw_claim.get("status") not in VALID_STATUSES:
            reject(index, "INVALID_STATUS", "status must be fact, inference, or hypothesis")
            continue
        status = raw_claim["status"]
        supporting = _uuid_list(raw_claim, "supporting_evidence_ids")
        if not supporting:
            supporting = _uuid_list(raw_claim, "evidence_id")
        contradicting = _uuid_list(raw_claim, "contradicting_evidence_ids")
        minimum = 2 if status == "inference" else 1
        limitations = [str(item) for item in raw_claim.get("limitations", []) if str(item).strip()]
        additional = [str(item) for item in raw_claim.get("required_additional_evidence", []) if str(item).strip()]
        reasoning = str(raw_claim.get("reasoning_summary") or "").strip() or None
        confidence = raw_claim.get("confidence")
        if raw_claim.get("evidence_id") and not _uuid_list(raw_claim, "evidence_id"):
            reject(index, "INVALID_EVIDENCE_ID", "evidence_id is not a valid UUID")
            continue
        if len(supporting) < minimum:
            reject(index, "MISSING_SUPPORT" if not supporting else "INSUFFICIENT_EVIDENCE",
                   f"{status} requires at least {minimum} supporting evidence IDs")
            continue
        if status == "inference" and not reasoning:
            reject(index, "MISSING_REASONING_SUMMARY", "inference requires reasoning_summary")
            continue
        if status == "inference" and not limitations:
            reject(index, "MISSING_LIMITATION", "inference requires limitations")
            continue
        if status == "hypothesis" and (not limitations or not additional):
            reject(index, "MISSING_LIMITATION" if not limitations else "INSUFFICIENT_EVIDENCE",
                   "hypothesis requires limitations and required_additional_evidence")
            continue
        if status == "hypothesis":
            try:
                if confidence is not None and float(confidence) > 0.79:
                    reject(index, "HYPOTHESIS_OVERCONFIDENCE", "hypothesis confidence must be <= 0.79")
                    continue
            except (TypeError, ValueError):
                reject(index, "HYPOTHESIS_OVERCONFIDENCE", "hypothesis confidence must be numeric")
                continue
        requested = set(supporting + contradicting)
        events = list(db.scalars(select(Event).where(Event.case_id == case_id, Event.event_id.in_(requested))))
        external = list(db.scalars(select(ExternalEvidence).where(ExternalEvidence.case_id == case_id, ExternalEvidence.evidence_id.in_(requested))))
        by_id = {event.event_id: event for event in [*events, *external]}
        if any(item not in by_id for item in requested):
            reject(index, "CROSS_CASE_EVIDENCE", "one or more evidence IDs are not in the active case")
            continue
        support_events = [by_id[item] for item in supporting]
        entities = {str(key): str(value) for key, value in (raw_claim.get("entities") or {}).items() if value is not None}
        if not _entity_consistent(entities, support_events):
            reject(index, "ENTITY_MISMATCH", "claim entity does not match supporting evidence")
            continue
        if contradicting and status == "fact" and any(item in by_id for item in contradicting):
            reject(index, "CONTRADICTORY_EVIDENCE_IGNORED",
                   "fact claim cannot ignore explicitly supplied contradicting evidence")
            continue
        for sentence in _sentences(str(raw_claim.get("text", ""))):
            if not _semantic_support(sentence, status, support_events):
                lower = sentence.lower()
                code = "UNSUPPORTED_SUCCESS_CLAIM" if any(word in lower for word in ("berhasil", "successful", "success")) else (
                    "UNSUPPORTED_FAILURE_CLAIM" if any(word in lower for word in ("gagal", "failed", "failure")) else "SEMANTIC_MISMATCH")
                reject(index, code, "claim wording is not supported by the selected events")
                continue
            verified.append(AgentClaim(
                claim_id=str(raw_claim.get("claim_id") or f"claim-{index + 1:03d}"),
                hypothesis_id=str(raw_claim.get("hypothesis_id")) if raw_claim.get("hypothesis_id") else None,
                text=sentence,
                status=status, evidence_id=supporting[0], supporting_evidence_ids=supporting,
                contradicting_evidence_ids=contradicting, entities=entities,
                confidence=float(confidence) if confidence is not None else None,
                reasoning_summary=reasoning, limitations=limitations,
                required_additional_evidence=additional, verification_status="verified",
                verification_reasons=[],
            ))
    if not verified:
        summary = {"verified_count": 0, "rejected_count": len(rejection_reasons),
                   "rejection_reasons": rejection_reasons}
        return ChatResponse(answer=INSUFFICIENT_EVIDENCE, claims=[],
                            verification_summary=summary), summary
    answer_parts = []
    for claim in verified:
        text = claim.text.rstrip(".!? ")
        citations = ", ".join(str(item) for item in claim.supporting_evidence_ids)
        answer_parts.append(f"{text} [evidence_ids: {citations}].")
    summary = {"verified_count": len(verified), "rejected_count": len(rejection_reasons),
               "rejection_reasons": rejection_reasons}
    return ChatResponse(answer=" ".join(answer_parts), claims=verified,
                        verification_summary=summary), summary


def verify_claims(db: Session, case_id: uuid.UUID, draft: dict) -> ChatResponse:
    return verify_claims_detailed(db, case_id, draft)[0]
