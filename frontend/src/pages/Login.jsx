import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Shield, Eye, EyeOff } from "lucide-react";
import { useAuthStore } from "../store";
import toast from "react-hot-toast";

export default function Login() {
  const [form,    setForm]    = useState({ username: "", password: "" });
  const [show,    setShow]    = useState(false);
  const [loading, setLoading] = useState(false);
  const login    = useAuthStore((s) => s.login);
  const navigate = useNavigate();

  const submit = async (e) => {
    e.preventDefault();
    if (!form.username || !form.password) return toast.error("Fill all fields");
    setLoading(true);
    try {
      await login(form.username, form.password);
      navigate("/dashboard");
    } catch (err) {
      toast.error(err.response?.data?.detail || "Login failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center p-4 scanlines"
         style={{ background: "var(--bg)" }}>
      {/* Background grid */}
      <div className="absolute inset-0 pointer-events-none" style={{
        backgroundImage: "linear-gradient(var(--border) 1px,transparent 1px),linear-gradient(90deg,var(--border) 1px,transparent 1px)",
        backgroundSize: "48px 48px",
        opacity: 0.3,
      }} />

      <div className="relative w-full max-w-sm fade-in">
        {/* Glow halo */}
        <div className="absolute inset-0 rounded-2xl blur-3xl"
             style={{ background: "radial-gradient(ellipse at center,rgba(0,212,255,0.08),transparent 70%)" }} />

        <div className="relative rounded-2xl p-8 box-glow" style={{ background: "var(--card)" }}>
          {/* Logo */}
          <div className="flex flex-col items-center mb-8">
            <div className="w-14 h-14 rounded-xl flex items-center justify-center mb-4"
                 style={{ background: "linear-gradient(135deg,rgba(0,212,255,0.2),rgba(124,58,237,0.2))",
                          border: "1px solid rgba(0,212,255,0.3)" }}>
              <Shield size={28} style={{ color: "var(--cyan)" }} />
            </div>
            <h1 className="text-xl font-bold mono tracking-widest" style={{ color: "var(--cyan)" }}>
              UNIPROXY
            </h1>
            <p className="text-xs mt-1" style={{ color: "var(--text-muted)" }}>
              Unified Proxy Management
            </p>
          </div>

          <form onSubmit={submit} className="space-y-4">
            <div>
              <label className="block text-xs uppercase tracking-widest mb-2"
                     style={{ color: "var(--text-muted)" }}>
                Username
              </label>
              <input
                type="text"
                autoComplete="username"
                value={form.username}
                onChange={(e) => setForm({ ...form, username: e.target.value })}
                className="w-full px-4 py-2.5 rounded-lg text-sm mono outline-none transition-all"
                style={{
                  background: "var(--surface)",
                  border: "1px solid var(--border)",
                  color: "var(--text)",
                }}
                onFocus={(e) => (e.target.style.borderColor = "var(--cyan)")}
                onBlur={(e)  => (e.target.style.borderColor = "var(--border)")}
                placeholder="admin"
              />
            </div>

            <div>
              <label className="block text-xs uppercase tracking-widest mb-2"
                     style={{ color: "var(--text-muted)" }}>
                Password
              </label>
              <div className="relative">
                <input
                  type={show ? "text" : "password"}
                  autoComplete="current-password"
                  value={form.password}
                  onChange={(e) => setForm({ ...form, password: e.target.value })}
                  className="w-full px-4 py-2.5 pr-10 rounded-lg text-sm mono outline-none transition-all"
                  style={{
                    background: "var(--surface)",
                    border: "1px solid var(--border)",
                    color: "var(--text)",
                  }}
                  onFocus={(e) => (e.target.style.borderColor = "var(--cyan)")}
                  onBlur={(e)  => (e.target.style.borderColor = "var(--border)")}
                  placeholder="••••••••"
                />
                <button
                  type="button"
                  onClick={() => setShow(!show)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 transition-colors"
                  style={{ color: "var(--text-muted)" }}
                >
                  {show ? <EyeOff size={14} /> : <Eye size={14} />}
                </button>
              </div>
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full py-2.5 rounded-lg font-semibold text-sm transition-all hover:opacity-90 disabled:opacity-50 mt-2"
              style={{
                background: loading
                  ? "var(--border)"
                  : "linear-gradient(135deg, var(--cyan), var(--violet))",
                color: "#fff",
              }}
            >
              {loading ? (
                <span className="flex items-center justify-center gap-2">
                  <svg className="animate-spin w-4 h-4" viewBox="0 0 24 24" fill="none">
                    <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" strokeDasharray="40" strokeDashoffset="10" />
                  </svg>
                  Authenticating...
                </span>
              ) : "Sign In"}
            </button>
          </form>

          <div className="mt-6 text-center text-xs mono" style={{ color: "var(--text-dim)" }}>
            UniProxy v1.0 · Secure by design
          </div>
        </div>
      </div>
    </div>
  );
}
