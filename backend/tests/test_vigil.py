import uuid

from app.claim_verifier import verify_claims_detailed
from app.vigil import (
    advance_lifecycle,
    build_contradiction_matrix,
    build_investigation_policy,
    ensure_vigil_state,
    initial_vigil_state,
    merge_hypotheses,
    public_state_summary,
    record_repair,
    record_result_provenance,
    record_tool_observation,
    revise_plan,
    select_next_action,
    set_stop,
)
from app.vigil_policy import (INVESTIGATION_STATES, VALID_TRANSITIONS, InvalidTransition,
                              lifecycle_state, rank_actions, transition_state)


class EvidenceDB:
    def __init__(self, events):
        self.events = events

    def scalars(self, _statement):
        return iter(self.events)


def test_plan_is_explicit_bounded_and_operational():
    case_id = uuid.uuid4()
    state = initial_vigil_state(case_id, "Apa rangkaian login pada case ini?", 6, 3, 2)

    assert state["state_schema_version"] == "vigil-state-v2"
    assert [step["step_id"] for step in state["plan"]["steps"]] == [
        "step-001", "step-002", "step-003", "step-004", "step-005"
    ]
    assert state["repair_state"]["max_attempts"] == 2
    assert public_state_summary(state)["plan"]["steps"][0]["status"] == "pending"


def test_valid_state_transitions_are_persisted():
    state = initial_vigil_state(uuid.uuid4(), "investigate", 5)
    advance_lifecycle(state, "PLANNING", "RUN_INITIALIZED")
    advance_lifecycle(state, "INVESTIGATING", "PLAN_ACCEPTED")
    advance_lifecycle(state, "EVIDENCE_REVIEW", "DRAFT_RETURNED")
    advance_lifecycle(state, "VERIFYING", "EVIDENCE_REVIEW_COMPLETE")
    advance_lifecycle(state, "COMPLETED", "CLAIMS_VERIFIED")
    assert lifecycle_state(state) == "COMPLETED"
    assert len(state["lifecycle"]["transition_history"]) == 5
    assert state["lifecycle"]["transition_history"][-1]["transition_reason"] == "CLAIMS_VERIFIED"


def test_invalid_state_transition_is_rejected():
    state = initial_vigil_state(uuid.uuid4(), "investigate", 5)
    advance_lifecycle(state, "PLANNING", "RUN_INITIALIZED")
    advance_lifecycle(state, "INVESTIGATING", "PLAN_ACCEPTED")
    advance_lifecycle(state, "EVIDENCE_REVIEW", "DRAFT_RETURNED")
    advance_lifecycle(state, "VERIFYING", "EVIDENCE_REVIEW_COMPLETE")
    advance_lifecycle(state, "COMPLETED", "CLAIMS_VERIFIED")
    try:
        advance_lifecycle(state, "INVESTIGATING", "should fail")
    except InvalidTransition:
        pass
    else:
        raise AssertionError("terminal state must reject implicit restart")


def test_every_declared_valid_transition_is_accepted():
    for current, targets in VALID_TRANSITIONS.items():
        for target in targets:
            state = initial_vigil_state(uuid.uuid4(), "transition", 3)
            state["current_state"] = current
            state["lifecycle"]["current_state"] = current
            transition_state(state, target, "matrix-test")
            assert lifecycle_state(state) == target


def test_every_undeclared_transition_is_rejected():
    for current in INVESTIGATION_STATES:
        for target in INVESTIGATION_STATES - VALID_TRANSITIONS.get(current, set()):
            state = initial_vigil_state(uuid.uuid4(), "transition", 3)
            state["current_state"] = current
            state["lifecycle"]["current_state"] = current
            try:
                transition_state(state, target, "matrix-test")
            except InvalidTransition:
                continue
            raise AssertionError(f"undeclared transition accepted: {current} -> {target}")


def test_policy_blocks_illegal_tool_and_repair_action():
    state = initial_vigil_state(uuid.uuid4(), "investigate", 1)
    policy = build_investigation_policy(1, max_repairs=0)
    assert not policy.can_call_tool(state, "shell_exec").allowed
    state["tool_call_count"] = 1
    assert not policy.can_call_tool(state, "search_events").allowed
    assert not policy.can_repair(state).allowed


def test_next_action_scoring_and_contradiction_matrix_are_explicit():
    actions = rank_actions([
        {"candidate_action": "search_disconfirming_evidence", "gap_priority": "high",
         "hypothesis_relevance": 0.9, "expected_evidence_value": 0.9,
         "reason_codes": ["HIGH_PRIORITY_GAP"]},
        {"candidate_action": "build_timeline", "gap_priority": "low",
         "hypothesis_relevance": 0.4, "expected_evidence_value": 0.4},
    ], remaining_budget=5)
    assert actions[0]["candidate_action"] == "search_disconfirming_evidence"
    assert isinstance(actions[0]["score"], float)
    state = initial_vigil_state(uuid.uuid4(), "investigate", 5)
    support = str(uuid.uuid4())
    contradiction = str(uuid.uuid4())
    neutral = str(uuid.uuid4())
    merge_hypotheses(state, [{"hypothesis_id": "H-001", "statement": "suspicious",
                              "status": "investigating", "supporting_evidence_ids": [support],
                              "contradicting_evidence_ids": [contradiction],
                              "neutral_evidence_ids": [neutral], "competition_group": "auth-explanation"}],
                     observed_ids={support, contradiction, neutral})
    matrix = build_contradiction_matrix(state)
    relations = {item["evidence_id"]: item["relation"] for item in matrix["H-001"]}
    assert relations == {support: "SUPPORTS", contradiction: "CONTRADICTS", neutral: "NEUTRAL"}
    assert state["hypothesis_competition"]["auth-explanation"][0]["hypothesis_id"] == "H-001"
    assert state["hypotheses"][0]["revision"] == 0


def test_plan_revision_is_bounded_and_allowlisted():
    state = initial_vigil_state(uuid.uuid4(), "investigate", 5, max_revisions=1)
    assert revise_plan(state, [{"step_id": "step-001", "objective": "Refine event search", "suggested_tools": ["search_events"]}], "new gap")
    assert state["plan"]["revision"] == 1
    assert not revise_plan(state, [{"step_id": "step-001", "suggested_tools": ["shell_exec"]}], "unsafe")
    assert not revise_plan(state, [{"step_id": "step-001", "objective": "again", "suggested_tools": ["search_events"]}], "too many")


def test_plan_step_transitions_when_selected_tool_is_observed():
    state = initial_vigil_state(uuid.uuid4(), "Apa rangkaian login gagal?", 5)
    action = select_next_action(state)
    assert action["plan_step_id"] == "step-001"
    assert state["plan"]["steps"][0]["status"] == "active"
    record_tool_observation(state, action["action"], [], 0, 1)
    assert state["plan"]["steps"][0]["status"] == "completed"
    assert "step-001" in state["completed_steps"]


def test_hypothesis_registry_creates_evidence_gaps_and_next_action():
    state = initial_vigil_state(uuid.uuid4(), "investigate", 5)
    evidence_id = str(uuid.uuid4())
    merge_hypotheses(state, [{
        "hypothesis_id": "H-001",
        "statement": "Rentetan login mungkin password guessing.",
        "status": "investigating",
        "supporting_evidence_ids": [evidence_id],
        "missing_evidence": ["Cari event scanner resmi"],
        "alternative_explanations": ["Pemantauan internal"],
    }])

    assert state["hypotheses"][0]["status"] == "investigating"
    assert any(gap["hypothesis_id"] == "H-001" for gap in state["evidence_gaps"])
    assert state["next_action"]["reason_code"] == "RESOLVE_EVIDENCE_GAP"
    assert "H-001" in state["epistemic_state"]["active_hypotheses"]

    record_tool_observation(state, "search_disconfirming_evidence", [evidence_id], 1, 2)
    assert state["action_history"][-1]["action"] == "search_disconfirming_evidence"
    assert evidence_id in state["collected_evidence_ids"]


def test_hypothesis_lifecycle_can_weaken_when_contradicting_evidence_arrives():
    state = initial_vigil_state(uuid.uuid4(), "investigate", 6)
    supporting_id = str(uuid.uuid4())
    contradicting_id = str(uuid.uuid4())
    merge_hypotheses(state, [{
        "hypothesis_id": "H-001", "statement": "Aktivitas mungkin password guessing.",
        "status": "investigating", "supporting_evidence_ids": [supporting_id],
    }], observed_ids={supporting_id})
    merge_hypotheses(state, [{
        "hypothesis_id": "H-001", "statement": "Aktivitas mungkin password guessing.",
        "status": "weakened", "supporting_evidence_ids": [supporting_id],
        "contradicting_evidence_ids": [contradicting_id],
        "alternative_explanations": ["Maintenance terotorisasi"],
    }], observed_ids={supporting_id, contradicting_id})

    hypothesis = state["hypotheses"][0]
    assert hypothesis["status"] == "weakened"
    assert hypothesis["contradicting_evidence_ids"] == [contradicting_id]
    assert any(item["from"] == "investigating" and item["to"] == "weakened"
               for item in hypothesis["history"])
    assert "H-001" in state["epistemic_state"]["rejected_hypotheses"]


def test_repair_and_stop_reason_are_structured():
    state = initial_vigil_state(uuid.uuid4(), "investigate", 5, max_repairs=1)
    attempt = record_repair(state, [{"reason_code": "MISSING_SUPPORT"}], "SEARCH_ADDITIONAL_EVIDENCE", "retry_requested")
    assert attempt == 1
    assert state["repair_state"]["attempts"][0]["action_taken"] == "SEARCH_ADDITIONAL_EVIDENCE"
    set_stop(state, "INSUFFICIENT_EVIDENCE", "no verified claim")
    assert state["stop_state"]["reason"] == "INSUFFICIENT_EVIDENCE"
    assert state["next_action"] is None


def test_case_memory_is_isolated_by_case_id():
    case_a, case_b = uuid.uuid4(), uuid.uuid4()
    evidence_a = str(uuid.uuid4())
    state_a = initial_vigil_state(case_a, "case A", 4)
    state_b = initial_vigil_state(case_b, "case B", 4)
    merge_hypotheses(state_a, [{
        "hypothesis_id": "H-A", "statement": "A", "status": "refuted",
        "supporting_evidence_ids": [evidence_a], "alternative_explanations": ["benign A"],
    }])
    assert state_a["case_memory"]["case_id"] == str(case_a)
    assert state_b["case_memory"]["case_id"] == str(case_b)
    assert evidence_a not in state_b["case_memory"]["relevant_evidence_ids"]
    assert "H-A" not in state_b["case_memory"]["rejected_hypotheses"]


def test_legacy_state_from_another_case_is_not_reused():
    case_a, case_b = uuid.uuid4(), uuid.uuid4()
    state_a = initial_vigil_state(case_a, "case A", 4)
    state_a["hypotheses"] = [{"hypothesis_id": "H-A", "statement": "private", "status": "supported"}]
    state_b = ensure_vigil_state(state_a, case_b, "case B", 4)
    assert state_b["case_id"] == str(case_b)
    assert state_b["hypotheses"] == []
    assert state_b["case_memory"]["case_id"] == str(case_b)


def test_provenance_links_events_correlations_findings_without_reasoning():
    state = initial_vigil_state(uuid.uuid4(), "case", 4)
    event_id = str(uuid.uuid4())
    correlation_id = str(uuid.uuid4())
    finding_id = str(uuid.uuid4())
    record_result_provenance(state, {
        "events": [{"event_id": event_id}],
        "correlations": [{"correlation_id": correlation_id, "event_id": event_id}],
        "findings": [{"finding_id": finding_id, "evidence_ids": [event_id]}],
    }, "build_timeline", "step-002")
    relations = {(edge["source_type"], edge["target_type"], edge["relation"]) for edge in state["provenance"]}
    assert ("evidence", "event", "projects_to") in relations
    assert ("event", "correlation", "linked_by") in relations
    assert ("finding", "evidence", "supported_by") in relations


def test_detailed_verifier_exposes_machine_readable_reason():
    event_id = uuid.uuid4()
    event = type("Event", (), {
        "event_id": event_id,
        "event_action": "login",
        "event_outcome": "failure",
        "username": "analyst",
        "source_ip": "192.0.2.10",
        "host": "host-a",
    })()
    response, summary = verify_claims_detailed(EvidenceDB([event]), uuid.uuid4(), {
        "claims": [{"text": "Login berhasil.", "status": "fact", "evidence_id": str(event_id)}]
    })
    assert response.claims == []
    assert summary["rejection_reasons"][0]["reason_code"] == "UNSUPPORTED_SUCCESS_CLAIM"
