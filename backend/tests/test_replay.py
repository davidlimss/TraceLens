import uuid

from app.models import AgentRun, AgentStep
from app.replay import create_run_snapshot, deterministic_trace_replay, diff_runs, snapshot_payload
from app.vigil import initial_vigil_state


def make_run(status="complete"):
    case_id = uuid.uuid4()
    run = AgentRun(
        case_id=case_id,
        question="Investigate authentication",
        state=initial_vigil_state(case_id, "Investigate authentication", 5),
        status=status,
        state_version="vigil-state-v2",
        prompt_version="prompt-v1",
        model_version="model-v1",
        graph_version="graph-v1",
        stop_reason="GOAL_SATISFIED",
    )
    run.agent_run_id = uuid.uuid4()
    run.state["collected_evidence_ids"] = [str(uuid.uuid4())]
    return run


def test_deterministic_trace_replay_does_not_call_llm():
    run = make_run()
    evidence_id = run.state["collected_evidence_ids"][0]
    step = AgentStep(
        agent_run_id=run.agent_run_id,
        case_id=run.case_id,
        step_number=1,
        step_type="tool",
        name="search_events",
        status="completed",
        input_data={"_vigil": {"plan_step_id": "step-001"}},
        output_data={"preview": "redacted"},
        evidence_ids=[uuid.UUID(evidence_id)],
        latency_ms=12,
    )
    result = deterministic_trace_replay(snapshot_payload(run, steps=[step]))
    assert result["llm_called"] is False
    assert result["observed_evidence_ids"] == [evidence_id]
    assert result["tool_trajectory"] == ["search_events"]
    assert result["replay_hash"]


def test_run_diff_is_descriptive_only():
    left = snapshot_payload(make_run())
    right = snapshot_payload(make_run())
    result = diff_runs(left, right)
    assert result["interpretation"] == "descriptive_only_no_quality_winner"
    assert "tool_count" in result["descriptive"]
    assert "stop_reason" in result["descriptive"]


def test_snapshot_has_stable_id_before_database_flush():
    class DB:
        def __init__(self):
            self.items = []

        def add(self, item):
            self.items.append(item)

    db = DB()
    snapshot = create_run_snapshot(db, make_run())
    assert snapshot.snapshot_id is not None
    assert db.items == [snapshot]
