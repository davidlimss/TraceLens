"use client";

import { FormEvent, useEffect, useState } from "react";
import { EvidenceModal } from "@/components/UI";
import { api } from "@/lib/api";
import type { ChatResponse, EventContext, EventItem } from "@/lib/types";

type Turn = { question: string; response?: ChatResponse; error?: string };

export default function Chat({ params }: { params: Promise<{ caseId: string }> }) {
  const [caseId, setCaseId] = useState("");
  const [question, setQuestion] = useState("Apa yang terjadi pada case ini?");
  const [turns, setTurns] = useState<Turn[]>([]);
  const [busy, setBusy] = useState(false);
  const [evidence, setEvidence] = useState<EventItem | null>(null);

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
    } catch (error) {
      setTurns((current) => current.map((turn, index) => index === current.length - 1
        ? { ...turn, error: error instanceof Error ? error.message : "Chat gagal" } : turn));
    } finally { setBusy(false); }
  }

  async function openEvidence(id: string) {
    try {
      const context = await api<EventContext>(`/cases/${caseId}/events/${id}`);
      setEvidence(context.event);
    } catch { /* Error stays non-disruptive to the conversation. */ }
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
            {turn.response.claims.length === 0 ? <div className="notice">Tidak ada claim yang lolos verification gate.</div>
              : turn.response.claims.map((claim, claimIndex) => {
                const supporting = [...new Set([claim.evidence_id, ...claim.supporting_evidence_ids])];
                return <article className={`claim claim-${claim.status}`} key={`${claim.evidence_id}-${claimIndex}`}>
                  <span className={`badge ${claim.status === "fact" ? "severity-info" : claim.status === "inference" ? "severity-high" : "severity-medium"}`}>{claim.status}</span>
                  {claim.confidence !== null && <span className="mono" style={{ marginLeft: 8, fontSize: 10 }}>confidence {(claim.confidence * 100).toFixed(0)}%</span>}
                  <p>{claim.text}</p>
                  {claim.reasoning_summary && <p><strong>Alasan:</strong> {claim.reasoning_summary}</p>}
                  {claim.limitations.length > 0 && <div className="notice"><strong>Keterbatasan:</strong> {claim.limitations.join("; ")}</div>}
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
