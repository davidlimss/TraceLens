"use client";
import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";

export default function Home() {
  const router=useRouter(); const [name,setName]=useState("Investigasi Log Baru");
  const [existing,setExisting]=useState(""); const [busy,setBusy]=useState(false); const [error,setError]=useState("");
  async function create(event:FormEvent){event.preventDefault();setBusy(true);setError("");try{const result=await api<{case_id:string}>("/cases",{method:"POST",body:JSON.stringify({name})});router.push(`/cases/${result.case_id}/dashboard`)}catch(reason){setError(reason instanceof Error?reason.message:"Gagal membuat case")}finally{setBusy(false)}}
  return <main className="gateway-screen"><section className="gateway-card card card-pad">
    <div className="gateway-kicker mono"><i/> DEFENSIVE OPERATIONS CONSOLE</div>
    <div className="brand gateway-brand"><strong>TRACE<span>LENS</span></strong><small>AI</small><em>EVIDENCE-GROUNDED SECURITY INVESTIGATION</em></div>
    <h1 className="page-title">Initialize case</h1><p className="page-subtitle">Buat investigation workspace baru atau buka case menggunakan UUID tervalidasi.</p>
    {error&&<div className="error" role="alert">{error}</div>}
    <form onSubmit={create}><label htmlFor="case-name">CASE DESIGNATION</label><input id="case-name" className="field" value={name} onChange={event=>setName(event.target.value)} required/><button className="btn primary gateway-action" disabled={busy}>{busy?"INITIALIZING...":"+ CREATE INVESTIGATION"}</button></form>
    <div className="gateway-divider"><span>OR RESUME</span></div>
    <label htmlFor="case-id">EXISTING CASE UUID</label><div className="gateway-open"><input id="case-id" className="field mono" value={existing} onChange={event=>setExisting(event.target.value)} placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"/><button className="btn" onClick={()=>existing&&router.push(`/cases/${existing}/dashboard`)}>OPEN</button></div>
  </section></main>;
}
