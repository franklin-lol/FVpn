import React, { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { Eye, EyeOff, Zap } from "lucide-react";
import { useAuthStore } from "../store";
import toast from "react-hot-toast";

export default function Login() {
  const [form,    setForm]    = useState({ username:"", password:"" });
  const [show,    setShow]    = useState(false);
  const [loading, setLoading] = useState(false);
  const login    = useAuthStore((s) => s.login);
  const token    = useAuthStore((s) => s.token);
  const navigate = useNavigate();

  useEffect(() => { if (token) navigate("/dashboard"); }, [token, navigate]);

  const submit = async (e) => {
    e.preventDefault();
    if (!form.username || !form.password) { toast.error("Fill all fields"); return; }
    setLoading(true);
    try {
      await login(form.username, form.password);
      navigate("/dashboard");
    } catch (err) {
      toast.error(err.response?.data?.detail || "Invalid credentials");
    } finally { setLoading(false); }
  };

  return (
    <div style={{ minHeight:"100vh", display:"flex", alignItems:"center", justifyContent:"center",
      background:"var(--bg)", padding:16, position:"relative", overflow:"hidden" }}>
      {/* Grid bg */}
      <div style={{ position:"absolute", inset:0, pointerEvents:"none",
        backgroundImage:"linear-gradient(var(--border) 1px,transparent 1px),linear-gradient(90deg,var(--border) 1px,transparent 1px)",
        backgroundSize:"52px 52px", opacity:.35 }} />
      {/* Glow */}
      <div style={{ position:"absolute", width:600, height:600, borderRadius:"50%", pointerEvents:"none",
        background:"radial-gradient(ellipse,rgba(0,212,255,.05) 0%,transparent 70%)",
        top:"50%", left:"50%", transform:"translate(-50%,-50%)" }} />

      <div className="fade-in" style={{ position:"relative", width:"100%", maxWidth:380 }}>
        <div style={{ background:"var(--card)", border:"1px solid var(--border-light)", borderRadius:16,
          padding:32, boxShadow:"0 32px 80px rgba(0,0,0,.55),0 0 0 1px rgba(0,212,255,.04) inset" }}>

          {/* Logo */}
          <div style={{ textAlign:"center", marginBottom:32 }}>
            <div style={{ width:50, height:50, borderRadius:14, margin:"0 auto 14px",
              background:"linear-gradient(135deg,rgba(0,212,255,.15),rgba(124,58,237,.15))",
              border:"1px solid rgba(0,212,255,.22)",
              display:"flex", alignItems:"center", justifyContent:"center",
              boxShadow:"0 0 28px rgba(0,212,255,.1)" }}>
              <Zap size={22} style={{ color:"var(--cyan)" }} />
            </div>
            <div style={{ fontFamily:"JetBrains Mono,monospace", fontWeight:700, fontSize:22,
              color:"var(--cyan)", letterSpacing:".08em", textShadow:"0 0 22px rgba(0,212,255,.35)" }}>
              FVpn
            </div>
            <div style={{ fontSize:12, color:"var(--text-muted)", marginTop:4, letterSpacing:".04em" }}>
              Proxy Management Panel
            </div>
          </div>

          {/* Form */}
          <form onSubmit={submit} style={{ display:"flex", flexDirection:"column", gap:14 }}>
            <div className="field">
              <label className="label field-label">Username</label>
              <input className="input" type="text" autoComplete="username"
                placeholder="admin" value={form.username} autoFocus
                onChange={(e) => setForm({ ...form, username:e.target.value })} />
            </div>
            <div className="field">
              <label className="label field-label">Password</label>
              <div style={{ position:"relative" }}>
                <input className="input" type={show?"text":"password"} autoComplete="current-password"
                  placeholder="••••••••" value={form.password} style={{ paddingRight:40 }}
                  onChange={(e) => setForm({ ...form, password:e.target.value })} />
                <button type="button" className="btn-icon"
                  style={{ position:"absolute", right:6, top:"50%", transform:"translateY(-50%)", border:"none" }}
                  onClick={() => setShow(!show)}>
                  {show ? <EyeOff size={14}/> : <Eye size={14}/>}
                </button>
              </div>
            </div>
            <button type="submit" disabled={loading}
              className="btn btn-primary btn-lg"
              style={{ marginTop:6, width:"100%", justifyContent:"center" }}>
              {loading ? <><div className="btn-spinner"/>Signing in…</> : "Sign in"}
            </button>
          </form>

          <div style={{ marginTop:22, textAlign:"center", fontFamily:"JetBrains Mono,monospace",
            fontSize:10, color:"var(--text-dim)", letterSpacing:".04em" }}>
            github.com/franklin-lol/FVpn
          </div>
        </div>
      </div>
    </div>
  );
}
