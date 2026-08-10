"use client";

import { FormEvent, useEffect, useState } from "react";
import { EvidenceModal } from "@/components/UI";
import { api } from "@/lib/api";
import type { AgentRunDetail, ChatResponse, EventContext, EventItem, ExternalEvidenceItem } from "@/lib/types";

type Turn = { question: string; response?: ChatResponse; error?: string };

export default function Chat({ params }: { params: Promise<{ caseId: string }> }) {
  const [caseId, setCaseId] = useState("");
  const [question, setQuestion] = useState("Apa yang terjadi pada case ini?");
  const [turns, setTurns] = useState<Turn[]>([]);
  const [busy, setBusy] = useState(false);
  const [evidence, setEvidence] = useState<EventItem | null>(null);
  const [runDetails, setRunDetails] = useState<Record<string, AgentRunDetail>>({});

  useEffect(() => { params.then((value) => setCaseId(value.caseId)); }, [params]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!question.trim() || busy) return;
    const asked = question.trim();
    setTurns((current) => [...current, { question: asked }]);
    setQuestion("");
    setBusy(true);
    try {
      const response = await api<ChatResponse>(`/cases/${caseId}/chat`, {
        method: "POST", body: JSON.stringify({ question: asked }),
      });
      setTurns((current) => current.map((turn, index) => index === current.length - 1 ? { ...turn, response } : turn));
      if (response.agent_run_id) {
        try {
          const detail = await api<AgentRunDetail>(`/cases/${caseId}/agent-runs/${response.agent_run_id}`);
          setRunDetails((current) => ({ ...current, [response.agent_run_id as string]: detail }));
        } catch { /* A trace failure must not hide a verified answer. */ }
      }
    } catch (error) {
      setTurns((current) => current.map((turn, index) => index === current.length - 1
        ? { ...turn, error: error instanceof Error ? error.message : "Chat gagal" } : turn));
    } finally { setBusy(false); }
  }

  async function openEvidence(id: string) {
    try {
      const context = await api<EventContext>(`/cases/${caseId}/events/${id}`);
      setEvidence(context.event);
    } catch {
      try {
        const external = await api<ExternalEvidenceItem>(`/cases/${caseId}/external-evidence/${id}`);
        setEvidence({
          event_id: external.evidence_id, timestamp_original: external.timestamp_original,
          timestamp_normalized: external.timestamp_normalized, timezone: null,
          source_type: external.provider, source_name: external.source_name, host: external.host,
          event_category: "external", event_action: external.event_action || "external_event",
          event_outcome: external.event_outcome, severity: external.severity, username: external.username,
          source_ip: external.source_ip, destination_ip: null, process_name: null, file_name: null,
          raw_log: external.raw_log, raw_line_number: external.raw_line_number || 0,
          parser_name: `${external.provider}-snapshot`, parser_confidence: 1, tags: external.tags,
          session_id: null, timestamp_confidence: 1, timestamp_assumptions: [], year_source: null, timezone_source: null,
        });
      } catch { /* Error stays non-disruptive to the conversation. */ }
    }
  }

  return <div className="content">
    <h1 className="page-title">AI Investigator Chat</h1>
    <p className="page-subtitle">Interpretasi AI dipisahkan dari claim dan evidence yang sudah diverifikasi backend.</p>
    <section className="card card-pad ai-panel">
      <div className="notice" style={{ marginBottom: 18 }}>✦ Agent hanya memakai tools database hasil parsing deterministik. Claim tanpa evidence valid dibuang oleh verification gate.</div>
      <div className="messages" aria-live="polite">
        {turns.length === 0 && <div className="empty">Ajukan pertanyaan tentang case ini.</div>}
        {turns.map((turn, index) => <div key={index}>
          <div className="user-msg">{turn.question}</div>
          {turn.error && <div className="error">{turn.error}</div>}
          {turn.response && <div className="ai-msg">
            <strong>✦ Narasi terverifikasi</strong><p>{turn.response.answer}</p>
            <InvestigationTrace state={turn.response.investigation} verification={turn.response.verification_summary} />
            {turn.response.agent_run_id && <DetailedAgentTrace detail={runDetails[turn.response.agent_run_id]} runId={turn.response.agent_run_id} />}
            {turn.response.claims.length === 0 ? <div className="notice">Tidak ada claim yang lolos verification gate.</div>
              : turn.response.claims.map((claim, claimIndex) => {
                const supporting = [...new Set([claim.evidence_id, ...claim.supporting_evidence_ids])];
                return <article className={`claim claim-${claim.status}`} key={`${claim.evidence_id}-${claimIndex}`}>
                  <span className={`badge ${claim.status === "fact" ? "severity-info" : claim.status === "inference" ? "severity-high" : "severity-medium"}`}>{claim.status}</span>
                  {claim.verification_status && <span className="badge severity-info" style={{ marginLeft: 8 }}>{claim.verification_status}</span>}
                  {claim.confidence !== null && <span className="mono" style={{ marginLeft: 8, fontSize: 10 }}>confidence {(claim.confidence * 100).toFixed(0)}%</span>}
                  <p>{claim.text}</p>
                  {claim.reasoning_summary && <p><strong>Alasan:</strong> {claim.reasoning_summary}</p>}
                  {claim.limitations.length > 0 && <div className="notice"><strong>Keterbatasan:</strong> {claim.limitations.join("; ")}</div>}
                  <details style={{ marginTop: 8 }}>
                    <summary style={{ cursor: "pointer" }}>Mengapa claim ini ditampilkan?</summary>
                    <div className="mono" style={{ fontSize: 11, marginTop: 6 }}>
                      status={claim.status} · verification={claim.verification_status || "unknown"} · evidence={supporting.length}
                      {claim.verification_reasons && claim.verification_reasons.length > 0 && <div style={{ marginTop: 4 }}>reason: {claim.verification_reasons.join("; ")}</div>}
                      <div style={{ marginTop: 4 }}>Claim hanya ditampilkan karena evidence ID dan dukungan semantiknya lolos pemeriksaan backend.</div>
                    </div>
                  </details>
                  <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginTop: 10 }}>
                    {supporting.map((id) => <button className="claim-cite" key={id} onClick={() => openEvidence(id)}>↗ evidence: {id}</button>)}
                  </div>
                  {claim.contradicting_evidence_ids.length > 0 && <div style={{ marginTop: 10 }}><strong>Evidence kontradiktif:</strong> {claim.contradicting_evidence_ids.map((id) => <button className="claim-cite" key={id} onClick={() => openEvidence(id)}>↗ {id}</button>)}</div>}
                  {claim.required_additional_evidence.length > 0 && <p><strong>Bukti tambahan yang diperlukan:</strong> {claim.required_additional_evidence.join("; ")}</p>}
                </article>;
              })}
          </div>}
        </div>)}
        {busy && <div className="loading">Agent sedang memilih tools dan memverifikasi bukti…</div>}
      </div>
      <form className="chat-form" onSubmit={submit}>
        <label className="sr-only" htmlFor="question">Pertanyaan investigasi</label>
        <textarea id="question" className="field" value={question} onChange={(event) => setQuestion(event.target.value)} placeholder="Tanya AI tentang insiden ini…" />
        <button className="btn ai" disabled={busy || !question.trim()}>Kirim</button>
      </form>
    </section>
    {evidence && <EvidenceModal event={evidence} onClose={() => setEvidence(null)} />}
  </div>;
}

function AgentTrace({ detail, runId }: { detail?: AgentRunDetail; runId: string }) {
  return <div className="notice" style={{ marginTop: 12 }}>
    <strong>Agent run durable</strong>
    <div className="mono" style={{ fontSize: 11, marginTop: 5 }}>run: {runId}</div>
    {detail ? <>
      <div style={{ marginTop: 6 }}>status: <span className="badge severity-info">{detail.run.status}</span> · steps: {detail.run.current_step} · evidence ledger: {detail.evidence_ledger.length}</div>
      <div className="mono" style={{ marginTop: 6, fontSize: 11 }}>jalur: {detail.steps.map((step) => `${step.step_type}:${step.name}`).join(" → ") || "belum ada step"}</div>
    </> : <div style={{ marginTop: 6 }}>Memuat trace tools dan checkpoint…</div>}
  </div>;
}

function DetailedAgentTrace({ detail, runId }: { detail?: AgentRunDetail; runId: string }) {
  if (!detail) {
    return <div className="notice" style={{ marginTop: 12 }}>Memuat trace tools dan checkpoint untuk run {runId}...</div>;
  }
  return <div className="notice" style={{ marginTop: 12 }}>
    <strong>Agent activity (operasional)</strong>
    <div className="mono" style={{ fontSize: 11, marginTop: 5 }}>run: {runId}</div>
    <div style={{ marginTop: 6 }}>
      status: <span className="badge severity-info">{detail.run.status}</span>
      {" · "}steps: {detail.run.current_step}
      {" · "}evidence ledger: {detail.evidence_ledger.length}
    </div>
    <div className="mono" style={{ fontSize: 10, marginTop: 4 }}>
      model: {detail.run.model_version || "unknown"} · prompt: {detail.run.prompt_version || "unknown"} · snapshots: {detail.snapshots?.length || 0}
    </div>
    <ol style={{ margin: "8px 0 0 20px" }}>
      {detail.steps.map((step) => {
        const input = step.input_data || {};
        const reason = typeof input.reason_code === "string" ? input.reason_code : "";
        const planStep = typeof input.plan_step_id === "string" ? input.plan_step_id : "";
        return <li key={step.agent_step_id} style={{ marginBottom: 6 }}>
          <span className="badge severity-info">{step.status}</span>{" "}
          <strong>{step.step_type}:{step.name}</strong>
          <span className="mono" style={{ marginLeft: 8, fontSize: 10 }}>
            {step.latency_ms ?? 0} ms · evidence {step.evidence_ids.length}
          </span>
          {(reason || planStep) && <div className="mono" style={{ fontSize: 10, marginTop: 2 }}>
            {reason || "step"}{planStep ? " · " + planStep : ""}
          </div>}
          {step.error_code && <div className="error" style={{ marginTop: 2 }}>{step.error_code}</div>}
        </li>;
      })}
    </ol>
  </div>;
}

function InvestigationTrace({ state, verification }: { state?: Record<string, unknown>; verification?: Record<string, unknown> }) {
  if (!state && !verification) return null;
  const plan = (state?.plan || {}) as Record<string, unknown>;
  const steps = Array.isArray(plan.steps) ? plan.steps as Record<string, unknown>[] : [];
  const hypotheses = Array.isArray(state?.hypotheses) ? state.hypotheses as Record<string, unknown>[] : [];
  const gaps = Array.isArray(state?.evidence_gaps) ? state.evidence_gaps as Record<string, unknown>[] : [];
  const memory = (state?.case_memory || {}) as Record<string, unknown>;
  const alternatives = Array.isArray(memory.known_benign_patterns) ? memory.known_benign_patterns as unknown[] : [];
  const nextAction = (state?.next_action || {}) as Record<string, unknown>;
  const lifecycle = (state?.lifecycle || {}) as Record<string, unknown>;
  const cost = (state?.cost_accounting || {}) as Record<string, unknown>;
  const progress = (state?.progress || {}) as Record<string, unknown>;
  const evidenceQuality = state?.evidence_quality && typeof state.evidence_quality === "object"
    ? Object.values(state.evidence_quality as Record<string, unknown>) as Record<string, unknown>[] : [];
  const contradictionMatrix = state?.contradiction_matrix && typeof state.contradiction_matrix === "object"
    ? state.contradiction_matrix as Record<string, unknown> : {};
  const stop = (state?.stop_state || {}) as Record<string, unknown>;
  const verified = Number(verification?.verified_count || 0);
  const rejected = Number(verification?.rejected_count || 0);
  const rejectionReasons = Array.isArray(verification?.rejection_reasons)
    ? verification.rejection_reasons as Record<string, unknown>[]
    : [];
  return <div className="notice" style={{ marginTop: 12 }}>
    <strong>Investigation trace (operasional, tanpa chain-of-thought)</strong>
    {typeof lifecycle.current_state === "string" && <div style={{ marginTop: 6 }}><strong>State:</strong> <span className="badge severity-info">{lifecycle.current_state}</span>
      {typeof lifecycle.transition_reason === "string" && <> · {lifecycle.transition_reason}</>}</div>}
    {typeof plan.investigation_goal === "string" && <p style={{ margin: "8px 0" }}><strong>Tujuan:</strong> {plan.investigation_goal}</p>}
    {steps.length > 0 && <div style={{ marginTop: 8 }}><strong>Rencana:</strong>
      <ol style={{ margin: "6px 0 0 20px" }}>{steps.map((step, index) => <li key={String(step.step_id || index)}>
        <span className="badge severity-info">{String(step.status || "pending")}</span> {String(step.objective || "")}
      </li>)}</ol>
    </div>}
    {hypotheses.length > 0 && <div style={{ marginTop: 8 }}><strong>Hypothesis:</strong>
      <ul style={{ margin: "6px 0 0 20px" }}>{hypotheses.map((item, index) => <li key={String(item.hypothesis_id || index)}>
        <span className="badge severity-medium">{String(item.status || "proposed")}</span> {String(item.statement || "")}
      </li>)}</ul>
    </div>}
    {hypotheses.length > 0 && <div style={{ marginTop: 8 }}><strong>Hypothesis evidence:</strong>
      <ul style={{ margin: "6px 0 0 20px" }}>{hypotheses.map((item, index) => {
        const supporting = Array.isArray(item.supporting_evidence_ids) ? item.supporting_evidence_ids.map(String) : [];
        const contradicting = Array.isArray(item.contradicting_evidence_ids) ? item.contradicting_evidence_ids.map(String) : [];
        const neutral = Array.isArray(item.neutral_evidence_ids) ? item.neutral_evidence_ids.map(String) : [];
        const missing = Array.isArray(item.missing_evidence) ? item.missing_evidence.map(String) : [];
        const itemAlternatives = Array.isArray(item.alternative_explanations) ? item.alternative_explanations.map(String) : [];
        return <li key={`evidence-${String(item.hypothesis_id || index)}`}>
          <strong>{String(item.hypothesis_id || index)}</strong>
          <div>Supporting: {supporting.join(", ") || "none"}</div>
          <div>Contradicting: {contradicting.join(", ") || "none"}</div>
          <div>Neutral: {neutral.join(", ") || "none"}</div>
          <div>Missing: {missing.join("; ") || "none"}</div>
          {itemAlternatives.length > 0 && <div>Alternatif: {itemAlternatives.join("; ")}</div>}
          {(contradicting.length > 0 || missing.length > 0 || itemAlternatives.length > 0) && <details style={{ marginTop: 4 }}>
            <summary style={{ cursor: "pointer" }}>Mengapa belum dianggap fakta?</summary>
            <div className="mono" style={{ fontSize: 11, marginTop: 4 }}>Hipotesis dibatasi karena terdapat bukti kontradiktif, bukti yang belum tersedia, atau alternatif benign.</div>
          </details>}
        </li>;
      })}</ul>
    </div>}
    {gaps.length > 0 && <div style={{ marginTop: 8 }}><strong>Evidence gap terbuka:</strong> {gaps.length}</div>}
    {alternatives.length > 0 && <div style={{ marginTop: 8 }}><strong>Alternatif/benign context:</strong> {alternatives.map(String).join("; ")}</div>}
    {typeof nextAction.action === "string" && <div style={{ marginTop: 8 }}><strong>Next action:</strong> {nextAction.action}
      {typeof nextAction.reason_code === "string" && <> <span className="badge severity-info">{nextAction.reason_code}</span></>}
    </div>}
    {(cost.tool_calls !== undefined || cost.model_calls !== undefined) && <div style={{ marginTop: 8 }}><strong>Budget/efficiency:</strong> tools {String(cost.tool_calls || 0)} · models {String(cost.model_calls || 0)} · elapsed {String(cost.elapsed_ms || 0)} ms · useful evidence {String(Array.isArray(progress.useful_evidence_ids) ? progress.useful_evidence_ids.length : 0)}</div>}
    {evidenceQuality.length > 0 && <div style={{ marginTop: 8 }}><strong>Evidence quality records:</strong> {evidenceQuality.length} (descriptive, bukan probabilitas serangan)</div>}
    {Object.keys(contradictionMatrix).length > 0 && <div style={{ marginTop: 8 }}><strong>Contradiction matrix:</strong> {Object.keys(contradictionMatrix).length} hypothesis terpetakan</div>}
    {(verified > 0 || rejected > 0) && <div style={{ marginTop: 8 }}><strong>Verification:</strong> {verified} lolos · {rejected} ditolak</div>}
    {rejectionReasons.length > 0 && <div style={{ marginTop: 8 }}><strong>Verification rejection reasons:</strong>
      <ul style={{ margin: "6px 0 0 20px" }}>{rejectionReasons.map((reason, index) => <li key={`rejection-${index}`}>
        <span className="badge severity-high">{String(reason.code || "rejected")}</span> {String(reason.detail || reason.message || "")}
      </li>)}</ul>
    </div>}
    {Boolean(stop.reason) && <div style={{ marginTop: 8 }}><strong>Stop reason:</strong> <span className="badge severity-info">{String(stop.reason)}</span></div>}
    {typeof stop.detail === "string" && <div style={{ marginTop: 8 }}><strong>Stop detail:</strong> {stop.detail}</div>}
  </div>;
}
