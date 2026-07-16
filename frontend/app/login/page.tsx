"use client";
import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";

export default function LoginPage(){const router=useRouter();const [username,setUsername]=useState("admin");const [password,setPassword]=useState("");const [error,setError]=useState("");const [busy,setBusy]=useState(false);
  useEffect(()=>{api("/auth/me").then(()=>router.replace("/")).catch(()=>{})},[router]);
  async function submit(event:FormEvent){event.preventDefault();setBusy(true);setError("");try{await api("/auth/login",{method:"POST",body:JSON.stringify({username,password})});router.replace("/")}catch(reason){setError(reason instanceof Error?reason.message:"Login gagal")}finally{setBusy(false)}}
  return <main className="gateway-screen"><form className="gateway-card auth-card card card-pad" onSubmit={submit}>
    <div className="gateway-kicker mono"><i/> ENCRYPTED SESSION REQUIRED</div><div className="brand gateway-brand"><strong>TRACE<span>LENS</span></strong><small>AI</small><em>AUTHORIZED SOC PERSONNEL ONLY</em></div>
    <h1 className="page-title">Authenticate</h1><p className="page-subtitle">Masuk menggunakan kredensial investigator yang diberikan administrator.</p>
    {error&&<div className="error" role="alert">{error}</div>}
    <label htmlFor="username">OPERATOR ID</label><input id="username" className="field" autoComplete="username" value={username} onChange={event=>setUsername(event.target.value)} required/>
    <label htmlFor="password">ACCESS KEY</label><input id="password" className="field" type="password" autoComplete="current-password" value={password} onChange={event=>setPassword(event.target.value)} required/>
    <button className="btn primary gateway-action" disabled={busy}>{busy?"AUTHENTICATING...":"AUTHENTICATE SESSION"}</button><p className="auth-notice mono">All access attempts are logged and attributable.</p>
  </form></main>}
