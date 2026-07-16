import re
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Event
from app.schemas import AgentClaim, ChatResponse

INSUFFICIENT_EVIDENCE = "Belum cukup bukti untuk menjawab pertanyaan ini."
VALID_STATUSES = {"fact", "inference", "hypothesis"}
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


def verify_claims(db: Session, case_id: uuid.UUID, draft: dict) -> ChatResponse:
    if not isinstance(draft, dict):
        return ChatResponse(answer=INSUFFICIENT_EVIDENCE, claims=[])
    verified: list[AgentClaim] = []
    for index, raw_claim in enumerate(draft.get("claims", [])):
        if not isinstance(raw_claim, dict) or raw_claim.get("status") not in VALID_STATUSES:
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
        if len(supporting) < minimum:
            continue
        if status == "inference" and (not reasoning or not limitations):
            continue
        if status == "hypothesis" and (not limitations or not additional):
            continue
        if status == "hypothesis" and confidence is not None and float(confidence) > 0.79:
            continue
        requested = set(supporting + contradicting)
        events = list(db.scalars(select(Event).where(Event.case_id == case_id, Event.event_id.in_(requested))))
        by_id = {event.event_id: event for event in events}
        if any(item not in by_id for item in requested):
            continue
        support_events = [by_id[item] for item in supporting]
        entities = {str(key): str(value) for key, value in (raw_claim.get("entities") or {}).items() if value is not None}
        if not _entity_consistent(entities, support_events):
            continue
        for sentence in _sentences(str(raw_claim.get("text", ""))):
            if not _semantic_support(sentence, status, support_events):
                continue
            verified.append(AgentClaim(
                claim_id=str(raw_claim.get("claim_id") or f"claim-{index + 1:03d}"), text=sentence,
                status=status, evidence_id=supporting[0], supporting_evidence_ids=supporting,
                contradicting_evidence_ids=contradicting, entities=entities,
                confidence=float(confidence) if confidence is not None else None,
                reasoning_summary=reasoning, limitations=limitations,
                required_additional_evidence=additional,
            ))
    if not verified:
        return ChatResponse(answer=INSUFFICIENT_EVIDENCE, claims=[])
    answer_parts = []
    for claim in verified:
        text = claim.text.rstrip(".!? ")
        citations = ", ".join(str(item) for item in claim.supporting_evidence_ids)
        answer_parts.append(f"{text} [evidence_ids: {citations}].")
    return ChatResponse(answer=" ".join(answer_parts), claims=verified)
