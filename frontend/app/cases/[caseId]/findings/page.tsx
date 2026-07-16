"use client";

import { useEffect, useMemo, useState } from "react";
import { Empty, ErrorState, Loading } from "@/components/UI";
import { api } from "@/lib/api";
import type { Finding } from "@/lib/types";

interface ExportResponse { export_id: string; format: "markdown" | "pdf"; content: string }

export default function Findings({ params }: { params: Promise<{ caseId: string }> }) {
  const [caseId, setCaseId] = useState("");
  const [data, setData] = useState<Finding[] | null>(null);
  const [error, setError] = useState("");
  const [exporting, setExporting] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  const [acknowledgeWarnings, setAcknowledgeWarnings] = useState(false);

  useEffect(() => {
    params.then(({ caseId: id }) => {
      setCaseId(id);
      api<Finding[]>(`/cases/${id}/findings`).then(setData).catch((requestError) => setError(requestError.message));
    });
  }, [params]);

  const risk = useMemo(() => data?.length ? Math.max(...data.map((finding) => finding.risk_score)) : 0, [data]);

  async function requestExport(format: "markdown" | "pdf") {
    setExporting(true);
    setError("");
    try {
      const report = await api<ExportResponse>(`/cases/${caseId}/exports`, {
        method: "POST", body: JSON.stringify({ format, acknowledge_warnings: acknowledgeWarnings }),
      });
      if (format === "markdown") {
        const blob = new Blob([report.content], { type: "text/markdown;charset=utf-8" });
        const url = URL.createObjectURL(blob);
        const anchor = document.createElement("a");
        anchor.href = url;
        anchor.download = `laporan-${caseId}-${report.export_id}.md`;
        anchor.click();
        URL.revokeObjectURL(url);
      } else {
        const binary = atob(report.content);
        const bytes = Uint8Array.from(binary, character => character.charCodeAt(0));
        const blob = new Blob([bytes], { type: "application/pdf" });
        const url = URL.createObjectURL(blob);
        const anchor = document.createElement("a");
        anchor.href = url;
        anchor.download = `laporan-investigasi-${caseId}-${report.export_id}.pdf`;
        anchor.click();
        URL.revokeObjectURL(url);
      }
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Export gagal");
    } finally {
      setExporting(false);
    }
  }

  async function rebuildAnalysis() {
    setAnalyzing(true); setError("");
    try {
      await api(`/cases/${caseId}/analysis/rebuild`, { method: "POST" });
      setData(await api<Finding[]>(`/cases/${caseId}/findings`));
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Analisis ulang gagal");
    } finally { setAnalyzing(false); }
  }

  async function updateWorkflow(finding: Finding, workflow_status: Finding["workflow_status"], disposition: string | null = finding.disposition) {
    setError("");
    try {
      const note = window.prompt("Catatan analis (opsional):") || null;
      const updated = await api<Finding>(`/cases/${caseId}/findings/${finding.finding_id}`, {
        method: "PATCH", body: JSON.stringify({ workflow_status, disposition, assigned_to: finding.assigned_to, note }),
      });
      setData((current) => current?.map((item) => item.finding_id === updated.finding_id ? updated : item) || []);
    } catch (requestError) { setError(requestError instanceof Error ? requestError.message : "Workflow gagal diperbarui"); }
  }

  if (error && !data) return <div className="content"><ErrorState error={error} /></div>;
  if (!data) return <div className="content"><Loading /></div>;

  return <div className="content">
    <div className="section-head">
      <div><h1 className="page-title">Findings & Report</h1><p className="page-subtitle" style={{ marginBottom: 0 }}>Temuan rule-based dan breakdown risk yang dapat diaudit.</p></div>
      <div className="no-print" style={{ display: "flex", gap: 10 }}>
        <button className="btn ai" disabled={analyzing || exporting} onClick={rebuildAnalysis}>{analyzing ? "Menganalisis..." : "Analisis Ulang"}</button>
        <button className="btn" disabled={exporting} onClick={() => requestExport("markdown")}>Export Markdown</button>
        <button className="btn danger" disabled={exporting} onClick={() => requestExport("pdf")}>Unduh PDF Investigasi</button>
      </div>
    </div>
    <label className="notice no-print" style={{ display: "flex", gap: 10, alignItems: "center", marginTop: 16 }}>
      <input type="checkbox" checked={acknowledgeWarnings} onChange={(event) => setAcknowledgeWarnings(event.target.checked)} />
      Saya mengakui bahwa evidence berstatus parsed_with_warnings mungkin tidak lengkap. Integritas hash tetap diverifikasi sebelum export.
    </label>
    {error && <ErrorState error={error} />}
    <section className="metric-grid" style={{ gridTemplateColumns: "repeat(3,1fr)", marginTop: 26 }}>
      <div className="card metric"><span className="metric-label">Risk Gabungan</span><div className="metric-value severity-high">{(risk * 100).toFixed(0)}%</div></div>
      <div className="card metric"><span className="metric-label">Jumlah Temuan</span><div className="metric-value">{data.length}</div></div>
      <div className="card metric"><span className="metric-label">Evidence Terkait</span><div className="metric-value">{new Set(data.flatMap((finding) => finding.evidence_ids)).size}</div></div>
    </section>
    <section style={{ marginTop: 26 }}>
      <h2>Temuan terdeteksi</h2>
      {data.length === 0 ? <div className="card"><Empty label="Belum ada temuan rule-based pada case ini." /></div> : data.map((finding) =>
        <article className="card finding" key={finding.finding_id}>
          <div><div className={`risk-orb severity-${finding.risk_score >= .85 ? "critical" : finding.risk_score >= .7 ? "high" : "medium"}`}>{(finding.risk_score * 100).toFixed(0)}</div></div>
          <div>
            <div className="section-head"><h2>{finding.title}</h2><span className="mono" style={{ fontSize: 10 }}>{finding.finding_id}</span></div>
            <p>{finding.description}</p>
            <div className="notice no-print" style={{display:"flex",gap:8,alignItems:"center",flexWrap:"wrap"}}>
              <strong>Status: {finding.workflow_status}</strong><span>Owner: {finding.assigned_to || "belum ditetapkan"}</span>
              <button className="btn" onClick={() => updateWorkflow(finding,"triaging")}>Ambil/Triage</button>
              <button className="btn" onClick={() => updateWorkflow(finding,"escalated","true_positive")}>Eskalasi</button>
              <button className="btn" onClick={() => updateWorkflow(finding,"closed","false_positive")}>Tutup FP</button>
              <button className="btn" onClick={() => updateWorkflow(finding,"closed","benign_positive")}>Tutup Benign</button>
            </div>
            <div className="event-meta" style={{ marginBottom: 8 }}><span>Confidence: <strong>{(finding.confidence_score * 100).toFixed(0)}%</strong></span><span>MITRE: <strong>{finding.mitre_technique || "Belum dipetakan"}</strong>{finding.mitre_tactic ? ` · ${finding.mitre_tactic}` : ""}</span></div>
            <div className="event-meta"><span>{finding.entity_type}: {finding.entity_value}</span><span>{new Date(finding.first_seen).toLocaleString("id-ID")} → {new Date(finding.last_seen).toLocaleString("id-ID")}</span></div>
            <div className="breakdown">{Object.entries(finding.risk_breakdown.components || {}).map(([name, component]) =>
              <div className="break-row" key={name}><span className="mono">{name}</span><div className="bar"><span style={{ width: `${Math.min(100, component.value * 100)}%` }} /></div><strong>{(component.contribution * 100).toFixed(0)}%</strong></div>)}</div>
            <details style={{ marginTop: 14 }}><summary className="mono" style={{ cursor: "pointer", fontSize: 11 }}>Evidence IDs ({finding.evidence_ids.length})</summary><div className="raw" style={{ marginTop: 8 }}>{finding.evidence_ids.join("\n")}</div></details>
            <details style={{ marginTop: 10 }}><summary style={{ cursor: "pointer" }}>Pertimbangan false positive</summary><ul>{(finding.false_positive_considerations || []).map((item) => <li key={item}>{item}</li>)}</ul></details>
            <details style={{ marginTop: 10 }}><summary style={{ cursor: "pointer" }}>Investigasi lanjutan</summary><ul>{(finding.recommended_queries || []).map((item) => <li key={item}>{item}</li>)}</ul></details>
            {finding.analyst_notes?.length > 0 && <details style={{marginTop:10}}><summary style={{cursor:"pointer"}}>Catatan analis ({finding.analyst_notes.length})</summary><ul>{finding.analyst_notes.map((note,index)=><li key={`${note.timestamp}-${index}`}><strong>{note.author}</strong> · {new Date(note.timestamp).toLocaleString("id-ID")} — {note.text}</li>)}</ul></details>}
          </div>
        </article>)}
    </section>
  </div>;
}
