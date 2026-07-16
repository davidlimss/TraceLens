"use client";

import { DragEvent, useEffect, useRef, useState } from "react";
import { api, uploadLog } from "@/lib/api";
import type { EvidenceFile } from "@/lib/types";

type QueueItem = { localId:string; file:File; progress:number; status:string; evidence?:EvidenceFile; error?:string };

export default function UploadPage({ params }: { params: Promise<{caseId:string}> }) {
  const [caseId,setCaseId]=useState("");
  const [queue,setQueue]=useState<QueueItem[]>([]);
  const [mode,setMode]=useState<"strict"|"quarantine">("strict");
  const [drag,setDrag]=useState(false);
  const input=useRef<HTMLInputElement>(null);
  useEffect(()=>{params.then(p=>setCaseId(p.caseId))},[params]);
  useEffect(()=>{
    const active=queue.filter(q=>q.evidence&&!['parsed','parsed_with_warnings','failed','cancelled','stuck'].includes(q.status));
    if(!active.length||!caseId)return;
    const timer=setInterval(()=>active.forEach(item=>api<EvidenceFile>(`/cases/${caseId}/jobs/${item.evidence!.job_id}`)
      .then(evidence=>setQueue(items=>items.map(current=>current.localId===item.localId?{...current,evidence,status:evidence.status,error:evidence.error_message??undefined}:current))).catch(()=>{})),1000);
    return()=>clearInterval(timer);
  },[queue,caseId]);
  async function add(files:FileList|File[]){
    for(const file of Array.from(files)){
      const localId=crypto.randomUUID(); setQueue(items=>[{localId,file,progress:0,status:'uploading'},...items]);
      try{
        const evidence=await uploadLog(caseId,file,progress=>setQueue(items=>items.map(x=>x.localId===localId?{...x,progress}:x)),mode) as EvidenceFile;
        setQueue(items=>items.map(x=>x.localId===localId?{...x,progress:100,status:evidence.status,evidence}:x));
      }catch(error){setQueue(items=>items.map(x=>x.localId===localId?{...x,status:'failed',error:error instanceof Error?error.message:'Upload gagal'}:x))}
    }
  }
  function drop(event:DragEvent){event.preventDefault();setDrag(false);add(event.dataTransfer.files)}
  return <div className="content">
    <h1 className="page-title">Unggah Berkas Log</h1>
    <p className="page-subtitle">SHA-256 dihitung saat ingestion; format dideteksi dari isi log.</p>
    <label htmlFor="parse-mode">Mode parsing</label>
    <select id="parse-mode" className="field" style={{maxWidth:320,margin:"8px 0 18px"}} value={mode} onChange={e=>setMode(e.target.value as "strict"|"quarantine")}>
      <option value="strict">Strict forensic — satu error menggagalkan file</option>
      <option value="quarantine">Quarantine — simpan baris valid dan tandai warning</option>
    </select>
    <div className="upload-layout">
      <section className={`dropzone card ${drag?'drag':''}`} onDragOver={e=>{e.preventDefault();setDrag(true)}} onDragLeave={()=>setDrag(false)} onDrop={drop} onClick={()=>input.current?.click()} role="button" tabIndex={0}>
        <input ref={input} type="file" multiple hidden onChange={e=>e.target.files&&add(e.target.files)}/><div className="drop-icon">⇧</div>
        <h2>Tarik & lepas berkas log di sini</h2><p>Linux, web access, JSON/JSONL, atau CSV generik.</p><button className="btn primary" type="button">Pilih berkas</button>
      </section>
      <aside className="card card-pad"><h2>Antrean unggahan</h2><div className="queue">
        {!queue.length&&<div className="empty">Belum ada unggahan.</div>}
        {queue.map(item=><div className={`queue-item ${item.status==='failed'?'failed':''}`} key={item.localId}>
          <div className="section-head"><strong className="mono">{item.file.name}</strong><span className="badge severity-info">{item.status}</span></div>
          <div className="event-meta"><span>{(item.file.size/1024).toFixed(1)} KB</span><span>{item.evidence?.detected_format||'mendeteksi…'}</span></div>
          {item.evidence&&<><div className="progress"><span style={{width:`${item.evidence.progress_percent}%`}}/></div><div className="event-meta"><span>{item.evidence.processed_lines}/{item.evidence.total_lines} baris</span><span>{item.evidence.malformed_lines} quarantine</span></div></>}
          {item.status==='uploading'&&<div className="progress"><span style={{width:`${item.progress}%`}}/></div>}{item.error&&<div className="error">{item.error}</div>}
        </div>)}
      </div></aside>
    </div>
  </div>;
}
