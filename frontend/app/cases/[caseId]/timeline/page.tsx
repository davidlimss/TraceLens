"use client";

import { useEffect, useMemo, useState } from "react";
import { Empty, ErrorState, EvidenceModal, Loading, RawLog, SeverityBadge } from "@/components/UI";
import { api } from "@/lib/api";
import type { EventItem, TimelinePage } from "@/lib/types";

export default function Timeline({ params }: { params: Promise<{ caseId: string }> }) {
  const [data, setData] = useState<TimelinePage | null>(null);
  const [selected, setSelected] = useState<EventItem | null>(null);
  const [severity, setSeverity] = useState("");
  const [source, setSource] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    params.then(({ caseId }) =>
      api<TimelinePage>(`/cases/${caseId}/timeline?page_size=200`).then(setData).catch((e) => setError(e.message)),
    );
  }, [params]);

  const filtered = useMemo(
    () => data?.items.filter((item) => (!severity || item.event.severity === severity) && (!source || item.event.source_type === source)) ?? [],
    [data, severity, source],
  );
  const sources = Array.from(new Set(data?.items.map((item) => item.event.source_type) ?? []));

  if (error) return <div className="content"><ErrorState error={error} /></div>;
  if (!data) return <div className="content"><Loading /></div>;

  return <div className="content">
    <h1 className="page-title">Timeline Insiden</h1>
    <p className="page-subtitle">Urutan deterministik lintas file. Klik event untuk melihat bukti mentah immutable.</p>
    <div className="filters">
      <label>Severity <select className="field" value={severity} onChange={(event) => setSeverity(event.target.value)}><option value="">Semua</option>{["info", "low", "medium", "high", "critical"].map((value) => <option key={value}>{value}</option>)}</select></label>
      <label>Source <select className="field" value={source} onChange={(event) => setSource(event.target.value)}><option value="">Semua</option>{sources.map((value) => <option key={value}>{value}</option>)}</select></label>
      <span className="notice">{filtered.length} / {data.total} event</span>
    </div>
    <section className="card card-pad">
      {filtered.length === 0 ? <Empty label="Tidak ada event untuk filter ini." /> : <div className="timeline">
        {filtered.map(({ event, correlations }) => <article className="timeline-item" id={`event-${event.event_id}`} key={event.event_id}>
          <span className={`timeline-dot severity-${event.severity}`} />
          <button className="event-button" onClick={() => setSelected(event)}>
            <div className="event-title"><time className="mono">{event.timestamp_normalized ? new Date(event.timestamp_normalized).toLocaleString("id-ID") : "Timestamp tidak tersedia"}</time><SeverityBadge severity={event.severity} /><span>{event.event_action}</span></div>
            <div className="event-meta"><span>{event.source_type}</span><span>{event.source_ip || event.username || event.host || event.source_name}</span><span>line {event.raw_line_number}</span></div>
            <RawLog event={event} compact />
          </button>
          {correlations.length > 0 && <div className="notice" style={{ marginTop: 9 }}>Terkorelasi: {correlations.slice(0, 3).map((correlation) => correlation.correlation_reason).join(" · ")}</div>}
        </article>)}
      </div>}
    </section>
    {selected && <EvidenceModal event={selected} onClose={() => setSelected(null)} />}
  </div>;
}
