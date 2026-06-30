import React, { useEffect, useState, useCallback } from "react";
import { Plus, Trash2, RefreshCw, Link, QrCode, Ban, CheckCircle2 } from "lucide-react";
import { usersApi, subsApi } from "../utils/api";
import toast from "react-hot-toast";
import QRCode from "react-qr-code";
import dayjs from "dayjs";

const FORMATS = ["singbox","clash","hiddify","shadowrocket","v2rayng","base64"];

function Sk({ h=14, w="100%", style={} }) {
  return <div className="skeleton" style={{ height:h, width:w, borderRadius:4, ...style }} />;
}

function Modal({ title, onClose, children, wide }) {
  return (
    <div className="overlay" onClick={(e) => e.target===e.currentTarget && onClose()}>
      <div className={`modal${wide?" modal-wide":""}`}>
        <div style={{ display:"flex", alignItems:"center", justifyContent:"space-between", marginBottom:20 }}>
          <h2 style={{ fontFamily:"JetBrains Mono,monospace", fontWeight:700, fontSize:15, color:"var(--cyan)" }}>{title}</h2>
          <button className="btn-icon" onClick={onClose} style={{ border:"none" }}>✕</button>
        </div>
        {children}
      </div>
    </div>
  );
}

function Field({ label, children }) {
  return (
    <div className="field">
      <label className="label field-label">{label}</label>
      {children}
    </div>
  );
}

function TrafficBar({ used, limit }) {
  if (limit === 0) return <span className="badge badge-cyan">Unlimited</span>;
  const pct = Math.min((used / limit) * 100, 100);
  const color = pct > 90 ? "var(--danger)" : pct > 70 ? "var(--warn)" : "var(--success)";
  return (
    <div style={{ minWidth:100 }}>
      <div style={{ display:"flex", justifyContent:"space-between", fontSize:11, marginBottom:3 }}>
        <span className="mono" style={{ color }}>{used.toFixed(1)}</span>
        <span style={{ color:"var(--text-muted)" }}>{limit} GB</span>
      </div>
      <div className="gauge-track">
        <div className="gauge-fill" style={{ width:`${pct}%`, background:color }} />
      </div>
    </div>
  );
}

function AddUserModal({ onClose, onCreated }) {
  const [form, setForm] = useState({ username:"", password:"", email:"", traffic_limit_gb:0, expire_at:"" });
  const [busy, setBusy] = useState(false);
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  const submit = async () => {
    if (!form.username || !form.password) { toast.error("Username and password required"); return; }
    setBusy(true);
    try {
      await usersApi.create({
        ...form,
        traffic_limit_gb: parseFloat(form.traffic_limit_gb) || 0,
        expire_at: form.expire_at || null,
      });
      toast.success("User created");
      onCreated(); onClose();
    } catch (e) { toast.error(e.response?.data?.detail || "Error"); }
    finally { setBusy(false); }
  };

  return (
    <Modal title="Create User" onClose={onClose}>
      <Field label="Username">
        <input className="input" value={form.username} onChange={set("username")} placeholder="john_doe" autoFocus />
      </Field>
      <Field label="Password">
        <input className="input" type="password" value={form.password} onChange={set("password")} placeholder="••••••••" />
      </Field>
      <Field label="Email (optional)">
        <input className="input" type="email" value={form.email} onChange={set("email")} placeholder="user@example.com" />
      </Field>
      <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr", gap:12 }}>
        <Field label="Traffic Limit GB (0=∞)">
          <input className="input" type="number" min="0" value={form.traffic_limit_gb} onChange={set("traffic_limit_gb")} />
        </Field>
        <Field label="Expires">
          <input className="input" type="date" value={form.expire_at} onChange={set("expire_at")} />
        </Field>
      </div>
      <button className="btn btn-primary" style={{ width:"100%", justifyContent:"center", marginTop:4 }} onClick={submit} disabled={busy}>
        {busy ? <><div className="btn-spinner"/>Creating…</> : "Create User"}
      </button>
    </Modal>
  );
}

function SubModal({ user, onClose }) {
  const [subs, setSubs]   = useState([]);
  const [fmt,  setFmt]    = useState("singbox");
  const [qrId, setQrId]   = useState(null);
  const [busy, setBusy]   = useState(false);

  const loadSubs = useCallback(async () => {
    try {
      const { data } = await subsApi.list();
      setSubs(data.filter((s) => s.user_id === user.id));
    } catch {}
  }, [user.id]);

  useEffect(() => { loadSubs(); }, [loadSubs]);

  const create = async () => {
    setBusy(true);
    try { await subsApi.create({ format: fmt }); toast.success("Subscription created"); loadSubs(); }
    catch (e) { toast.error(e.response?.data?.detail || "Error"); }
    finally { setBusy(false); }
  };

  const del = async (id) => {
    try { await subsApi.delete(id); loadSubs(); }
    catch { toast.error("Delete failed"); }
  };

  return (
    <Modal title={`Subscriptions — ${user.username}`} onClose={onClose}>
      <div style={{ display:"flex", gap:8, marginBottom:14 }}>
        <select className="input select" style={{ flex:1 }} value={fmt} onChange={(e) => setFmt(e.target.value)}>
          {FORMATS.map((f) => <option key={f} value={f}>{f}</option>)}
        </select>
        <button className="btn btn-primary btn-sm" onClick={create} disabled={busy}>
          {busy ? <div className="btn-spinner"/> : "+ New"}
        </button>
      </div>

      <div style={{ display:"flex", flexDirection:"column", gap:8, maxHeight:320, overflow:"auto" }} className="no-scrollbar">
        {subs.length === 0 ? (
          <div className="empty" style={{ padding:"20px 0" }}>
            <p>No subscriptions yet</p>
          </div>
        ) : subs.map((s) => (
          <div key={s.id} style={{ background:"var(--surface)", border:"1px solid var(--border)", borderRadius:8, padding:12 }}>
            <div style={{ display:"flex", alignItems:"center", justifyContent:"space-between", marginBottom:6 }}>
              <span className="badge badge-violet">{s.format}</span>
              <div style={{ display:"flex", gap:4 }}>
                <button className="btn-icon" title="Copy URL"
                  onClick={() => { navigator.clipboard.writeText(s.url); toast.success("Copied!"); }}
                  style={{ color:"var(--cyan)" }}>
                  <Link size={12}/>
                </button>
                <button className="btn-icon" title="QR Code"
                  onClick={() => setQrId(qrId === s.id ? null : s.id)}
                  style={{ color:"var(--success)" }}>
                  <QrCode size={12}/>
                </button>
                <button className="btn-icon" title="Delete" onClick={() => del(s.id)} style={{ color:"var(--danger)" }}>
                  <Trash2 size={12}/>
                </button>
              </div>
            </div>
            <div className="mono truncate" style={{ fontSize:11, color:"var(--text-muted)" }}>{s.url}</div>
            {qrId === s.id && (
              <div style={{ display:"flex", justifyContent:"center", marginTop:10, padding:12, background:"#fff", borderRadius:8 }}>
                <QRCode value={s.url} size={140}/>
              </div>
            )}
          </div>
        ))}
      </div>
    </Modal>
  );
}

export default function Users() {
  const [users,   setUsers]   = useState([]);
  const [loading, setLoading] = useState(true);
  const [addOpen, setAddOpen] = useState(false);
  const [subUser, setSubUser] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try { const { data } = await usersApi.list(); setUsers(data); }
    catch { toast.error("Failed to load users"); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const del = async (id) => {
    if (!confirm("Delete this user?")) return;
    try { await usersApi.delete(id); toast.success("User deleted"); load(); }
    catch { toast.error("Delete failed"); }
  };

  const toggle = async (u) => {
    try { await usersApi.update(u.id, { is_active: !u.is_active }); load(); }
    catch { toast.error("Update failed"); }
  };

  const reset = async (id) => {
    try { await usersApi.resetTraffic(id); toast.success("Traffic reset"); load(); }
    catch { toast.error("Reset failed"); }
  };

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <div className="page-title">Users</div>
          <div className="page-sub">{users.length} account{users.length !== 1 ? "s" : ""}</div>
        </div>
        <button className="btn btn-primary btn-sm" onClick={() => setAddOpen(true)}>
          <Plus size={13}/>Create User
        </button>
      </div>

      {loading ? (
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>{["User","Status","Traffic","Expires","",""].map((h,i)=><th key={i}>{h}</th>)}</tr>
            </thead>
            <tbody>
              {[1,2,3].map((k)=>(
                <tr key={k}><td colSpan={6} style={{ padding:12 }}><Sk h={12}/></td></tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>User</th><th>Status</th><th>Traffic</th>
                <th>Expires</th><th>Sub</th><th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {users.length === 0 ? (
                <tr><td colSpan={6}>
                  <div className="empty" style={{ padding:"28px 0" }}>
                    <h3>No users yet</h3>
                    <p>Create your first user to generate subscription links</p>
                    <button className="btn btn-primary btn-sm" onClick={() => setAddOpen(true)} style={{ marginTop:8 }}>
                      <Plus size={13}/>Create User
                    </button>
                  </div>
                </td></tr>
              ) : users.map((u) => {
                const active = u.is_active && !u.is_expired;
                return (
                  <tr key={u.id}>
                    <td>
                      <div style={{ fontWeight:600 }}>{u.username}</div>
                      {u.email && <div style={{ fontSize:11, color:"var(--text-muted)" }}>{u.email}</div>}
                      {u.is_admin && <span className="badge badge-violet" style={{ marginTop:2 }}>admin</span>}
                    </td>
                    <td>
                      <span className={`badge badge-${active?"green":"red"}`}>
                        <span className={`dot dot-${active?"online":"offline"}`} style={{width:5,height:5}}/>
                        {!u.is_active ? "Disabled" : u.is_expired ? "Expired" : "Active"}
                      </span>
                    </td>
                    <td><TrafficBar used={u.traffic_used_gb} limit={u.traffic_limit_gb}/></td>
                    <td>
                      <span className="mono" style={{ fontSize:12, color:"var(--text-muted)" }}>
                        {u.expire_at ? dayjs(u.expire_at).format("YYYY-MM-DD") : "Never"}
                      </span>
                    </td>
                    <td>
                      <button className="btn btn-ghost btn-sm" onClick={() => setSubUser(u)}>
                        <Link size={11}/>Links
                      </button>
                    </td>
                    <td>
                      <div style={{ display:"flex", gap:4 }}>
                        <button className="btn-icon" onClick={() => toggle(u)} title={u.is_active?"Disable":"Enable"}
                          style={{ color: u.is_active?"var(--warn)":"var(--success)" }}>
                          {u.is_active ? <Ban size={13}/> : <CheckCircle2 size={13}/>}
                        </button>
                        <button className="btn-icon" onClick={() => reset(u.id)} title="Reset traffic" style={{ color:"var(--cyan)" }}>
                          <RefreshCw size={13}/>
                        </button>
                        <button className="btn-icon" onClick={() => del(u.id)} title="Delete" style={{ color:"var(--danger)" }}>
                          <Trash2 size={13}/>
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {addOpen && <AddUserModal onClose={() => setAddOpen(false)} onCreated={load}/>}
      {subUser  && <SubModal user={subUser} onClose={() => setSubUser(null)}/>}
    </div>
  );
}
