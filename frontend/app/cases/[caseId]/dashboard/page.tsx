"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { Empty, ErrorState, Loading, SeverityBadge } from "@/components/UI";
import { api } from "@/lib/api";
import type { Entity, EvidenceFile, Finding, TimelinePage } from "@/lib/types";

const CHART_COLORS=["var(--info)","var(--medium)","var(--high)","var(--critical)","var(--ai)","var(--low)"];

function countBy(values:(string|null|undefined)[]){return values.reduce<Record<string,number>>((counts,value)=>{const key=(value||"unknown").toLowerCase();counts[key]=(counts[key]||0)+1;return counts},{})}
function entries(counts:Record<string,number>){return Object.entries(counts).sort((a,b)=>b[1]-a[1])}
function DonutChart({title,data}:{title:string;data:[string,number][]}){const total=data.reduce((sum,[,value])=>sum+value,0);let cursor=0;const gradient=data.length?data.map(([label,value],index)=>{const start=cursor;cursor+=total?value/total*100:0;return `${CHART_COLORS[index%CHART_COLORS.length]} ${start}% ${cursor}%`}).join(","):"var(--surface-3) 0 100%";return <section className="card card-pad chart-card" aria-label={`${title}, total ${total} event`}><div className="section-head"><h2>{title}</h2><span className="chart-scope">{total} event</span></div><div className="donut-layout"><div className="donut" role="img" aria-label={data.map(([label,value])=>`${label} ${value}`).join(", ")} style={{background:`conic-gradient(${gradient})`}}><span>{total}</span></div><div className="chart-legend">{data.length?data.slice(0,6).map(([label,value],index)=><div className="legend-row" key={label}><span className="legend-dot" style={{background:CHART_COLORS[index%CHART_COLORS.length]}}/><span>{label}</span><strong>{value}</strong></div>):<span className="chart-scope">Belum ada data</span>}</div></div></section>}
function BarChart({title,data}:{title:string;data:[string,number][]}){const max=Math.max(1,...data.map(([,value])=>value));return <section className="card card-pad chart-card"><div className="section-head"><h2>{title}</h2><span className="chart-scope">Top {Math.min(6,data.length)}</span></div><div className="horizontal-chart">{data.slice(0,6).map(([label,value],index)=><div className="chart-row" key={label}><span title={label}>{label}</span><div className="chart-track"><i style={{width:`${value/max*100}%`,background:CHART_COLORS[index%CHART_COLORS.length]}}/></div><strong>{value}</strong></div>)}</div></section>}

export default function Dashboard({ params }: { params: Promise<{caseId:string}> }) {
  const [caseId,setCaseId]=useState(""); const [timeline,setTimeline]=useState<TimelinePage|null>(null);
  const [entities,setEntities]=useState<Entity[]>([]); const [findings,setFindings]=useState<Finding[]>([]);
  const [logs,setLogs]=useState<EvidenceFile[]>([]); const [error,setError]=useState("");
  useEffect(()=>{params.then(({caseId:id})=>{setCaseId(id);Promise.all([
    api<TimelinePage>(`/cases/${id}/timeline?page_size=200`),api<Entity[]>(`/cases/${id}/entities`),
    api<Finding[]>(`/cases/${id}/findings`),api<EvidenceFile[]>(`/cases/${id}/logs`)
  ]).then(([t,e,f,l])=>{setTimeline(t);setEntities(e);setFindings(f);setLogs(l)}).catch(requestError=>setError(requestError.message))})},[params]);
  const summary=useMemo(()=>{const events=timeline?.items.map(item=>item.event)??[];const dates=events.filter(e=>e.timestamp_normalized).map(e=>new Date(e.timestamp_normalized!));
    const users=entities.filter(e=>e.entity_type==='username'),ips=entities.filter(e=>e.entity_type==='source_ip');
    return {events,users,ips,hosts:new Set(events.map(e=>e.host).filter(Boolean)).size,risk:findings.length?Math.max(...findings.map(f=>f.risk_score)):0,
      severity:entries(countBy(events.map(e=>e.severity))),outcomes:entries(countBy(events.map(e=>e.event_outcome))),sources:entries(countBy(events.map(e=>e.source_type))),
      topIps:ips.map(e=>[e.entity_value,e.event_count] as [string,number]).sort((a,b)=>b[1]-a[1]),
      mitre:entries(countBy(findings.map(f=>f.mitre_technique))),
      start:dates.length?new Date(Math.min(...dates.map(d=>d.getTime()))):null,end:dates.length?new Date(Math.max(...dates.map(d=>d.getTime()))):null}},[timeline,entities,findings]);
  if(error)return <div className="content"><ErrorState error={error}/></div>; if(!timeline)return <div className="content"><Loading/></div>;
  const riskSeverity=summary.risk>=.85?'critical':summary.risk>=.7?'high':summary.risk>=.4?'medium':'info';
  return <div className="content"><h1 className="page-title">Ringkasan Investigasi</h1><p className="page-subtitle">Status evidence, cakupan entity, dan risiko tertinggi case.</p>
    <section className="metric-grid"><div className="card metric"><span className="metric-label">Skor Risiko</span><div className={`metric-value severity-${riskSeverity}`}>{(summary.risk*100).toFixed(0)}%</div><span className="metric-meta">normalized · uncalibrated</span></div>
      <div className="card metric"><span className="metric-label">Berkas Log</span><div className="metric-value">{logs.length}</div><span className="metric-meta">{logs.filter(l=>l.status.startsWith('parsed')).length} parsed</span></div>
      <div className="card metric"><span className="metric-label">Event Terstruktur</span><div className="metric-value">{timeline.total}</div><span className="metric-meta">deterministik</span></div>
      <div className="card metric"><span className="metric-label">Entity Terdampak</span><div className="metric-value">{summary.hosts+summary.users.length+summary.ips.length}</div><span className="metric-meta">host · user · IP</span></div></section>
    {logs.some(log=>log.status==='parsed_with_warnings'||log.integrity_status==='mismatch')&&<div className="error">Data quality warning: periksa quarantine atau integrity evidence sebelum membuat laporan.</div>}
    <div className="dashboard-charts"><DonutChart title="Distribusi Severity" data={summary.severity}/><DonutChart title="Distribusi Outcome" data={summary.outcomes}/><BarChart title="Sumber Event" data={summary.sources}/><BarChart title="Top Source IP" data={summary.topIps}/><BarChart title="Temuan MITRE ATT&CK" data={summary.mitre}/></div>
    <section className="card card-pad rundown-card"><div className="section-head"><div><h2>Rundown hasil analisis</h2><p className="chart-scope">Urutan deterministik dari event yang dimuat, bukan narasi buatan LLM.</p></div><Link className="btn ai" href={`/cases/${caseId}/chat`}>Tanya Penyidik AI</Link></div>
      {!summary.events.length?<Empty label="Rundown akan muncul setelah log selesai diproses."/>:<ol className="rundown">{summary.events.slice(0,10).map((event,index)=><li key={event.event_id}><span className={`rundown-index severity-${event.severity}`}>{String(index+1).padStart(2,'0')}</span><div><div className="event-title"><span>{event.event_action}</span><SeverityBadge severity={event.severity}/>{event.event_outcome&&<span className="badge">{event.event_outcome}</span>}</div><p>{event.timestamp_normalized?new Date(event.timestamp_normalized).toLocaleString('id-ID'):'Waktu tidak tersedia'} · {event.source_ip||event.username||event.host||event.source_name}</p><span className="mono rundown-evidence">evidence {event.event_id} · baris {event.raw_line_number}</span></div></li>)}</ol>}
      {timeline.total>summary.events.length&&<div className="notice">Visual dan rundown memakai {summary.events.length} dari {timeline.total} event. Buka Timeline untuk melihat keseluruhan evidence.</div>}
    </section>
    <div className="grid-2"><section className="card card-pad"><div className="section-head"><h2>Timeline terbaru</h2><Link className="btn" href={`/cases/${caseId}/timeline`}>Buka timeline</Link></div>
      {!summary.events.length?<Empty label="Belum ada event. Unggah log untuk memulai."/>:<div className="timeline">{summary.events.slice(0,6).map(event=><div className="timeline-item" key={event.event_id}><span className={`timeline-dot severity-${event.severity}`}/><div className="event-title"><span>{event.event_action}</span><SeverityBadge severity={event.severity}/></div><div className="event-meta"><span>{event.timestamp_normalized?new Date(event.timestamp_normalized).toLocaleString('id-ID'):'Tanpa timestamp'}</span><span>{event.source_ip||event.username||event.host||event.source_name}</span></div>{event.timestamp_assumptions.length>0&&<div className="event-meta">Timestamp confidence {(event.timestamp_confidence*100).toFixed(0)}% · {event.timestamp_assumptions.join('; ')}</div>}</div>)}</div>}
    </section><aside className="card card-pad"><h2>Cakupan investigasi</h2><p className="notice">Rentang: {summary.start?.toLocaleString('id-ID')??'—'} → {summary.end?.toLocaleString('id-ID')??'—'}</p><h3>IP</h3><div className="stat-list">{summary.ips.slice(0,8).map(e=><span className="entity-pill" key={e.entity_value}>{e.entity_value} · {e.event_count}</span>)}</div><h3>Pengguna</h3><div className="stat-list">{summary.users.slice(0,8).map(e=><span className="entity-pill" key={e.entity_value}>{e.entity_value} · {e.event_count}</span>)}</div></aside></div>
  </div>;
}
