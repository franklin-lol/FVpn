import React, { useEffect, useState, useCallback } from "react";
import { Plus, Trash2, RefreshCw, Link, QrCode, Ban, CheckCircle2 } from "lucide-react";
import { usersApi, subsApi } from "../utils/api";
import toast from "react-hot-toast";
import QRCode from "react-qr-code";
import dayjs from "dayjs";

const FORMATS = ["singbox","clash","hiddify","shadowrocket","v2rayng","base64"];

function Modal({ title, onClose, children }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" style={{background:"rgba(0,0,0,0.75)"}}>
      <div className="w-full max-w-lg rounded-xl p-6 box-glow" style={{background:"var(--card)"}}>
        <div className="flex items-center justify-between mb-5">
          <h2 className="font-bold mono" style={{color:"var(--cyan)"}}>{title}</h2>
          <button onClick={onClose} className="text-slate-500 hover:text-slate-300 text-xl leading-none">×</button>
        </div>
        {children}
      </div>
    </div>
  );
}

const inp = "w-full px-3 py-2 rounded text-sm mono outline-none focus:ring-1";
const inpStyle = { background:"var(--surface)", border:"1px solid var(--border)", color:"var(--text)" };

function Field({ label, children }) {
  return (
    <div className="mb-3">
      <label className="block text-xs mb-1" style={{color:"var(--text-muted)"}}>{label}</label>
      {children}
    </div>
  );
}

function AddUserModal({ onClose, onCreated }) {
  const [form, setForm] = useState({
    username:"", password:"", email:"", traffic_limit_gb:0, expire_at:""
  });
  const [busy, setBusy] = useState(false);
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  const submit = async () => {
    if (!form.username || !form.password) return toast.error("Username and password required");
    setBusy(true);
    try {
      const payload = {
        ...form,
        traffic_limit_gb: parseFloat(form.traffic_limit_gb) || 0,
        expire_at: form.expire_at || null,
      };
      await usersApi.create(payload);
      toast.success("User created");
      onCreated(); onClose();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Error");
    } finally { setBusy(false); }
  };

  return (
    <Modal title="Create User" onClose={onClose}>
      <Field label="Username">
        <input className={inp} style={inpStyle} value={form.username} onChange={set("username")} placeholder="john_doe" />
      </Field>
      <Field label="Password">
        <input className={inp} style={inpStyle} type="password" value={form.password} onChange={set("password")} />
      </Field>
      <Field label="Email (optional)">
        <input className={inp} style={inpStyle} type="email" value={form.email} onChange={set("email")} />
      </Field>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Traffic Limit (GB, 0=∞)">
          <input className={inp} style={inpStyle} type="number" min="0" value={form.traffic_limit_gb}
                 onChange={set("traffic_limit_gb")} />
        </Field>
        <Field label="Expire Date">
          <input className={inp} style={inpStyle} type="date" value={form.expire_at} onChange={set("expire_at")} />
        </Field>
      </div>
      <button onClick={submit} disabled={busy}
        className="w-full mt-2 py-2 rounded font-semibold text-sm hover:opacity-90"
        style={{background:"linear-gradient(135deg,var(--cyan),var(--violet))",color:"#fff"}}>
        {busy ? "Creating..." : "Create User"}
      </button>
    </Modal>
  );
}

function SubModal({ user, onClose }) {
  const [subs, setSubs] = useState([]);
  const [fmt,  setFmt]  = useState("singbox");
  const [qrSub, setQrSub] = useState(null);
  const [busy, setBusy] = useState(false);

  const loadSubs = useCallback(async () => {
    try {
      const { data } = await subsApi.list();
      setSubs(data.filter((s) => s.user_id === user.id));
    } catch {}
  }, [user.id]);

  useEffect(() => { loadSubs(); }, [loadSubs]);

  const create = async () => {
    setBusy(true);
    try {
      await subsApi.create({ format: fmt });
      toast.success("Subscription created");
      loadSubs();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Error");
    } finally { setBusy(false); }
  };

  const del = async (id) => {
    try { await subsApi.delete(id); loadSubs(); }
    catch { toast.error("Delete failed"); }
  };

  return (
    <Modal title={`Subscriptions — ${user.username}`} onClose={onClose}>
      {/* Create new */}
      <div className="flex gap-2 mb-4">
        <select className={inp} style={inpStyle} value={fmt} onChange={(e) => setFmt(e.target.value)}>
          {FORMATS.map((f) => <option key={f} value={f}>{f}</option>)}
        </select>
        <button onClick={create} disabled={busy}
          className="px-4 py-2 rounded text-sm font-semibold flex-shrink-0 hover:opacity-90"
          style={{background:"var(--cyan)",color:"#000"}}>
          + New
        </button>
      </div>

      {/* List */}
      <div className="space-y-3 max-h-64 overflow-y-auto">
        {subs.map((s) => (
          <div key={s.id} className="rounded-lg p-3" style={{background:"var(--surface)",border:"1px solid var(--border)"}}>
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs px-2 py-0.5 rounded mono"
                    style={{background:"var(--violet)20",color:"var(--violet)"}}>
                {s.format}
              </span>
              <div className="flex gap-2">
                <button onClick={() => { navigator.clipboard.writeText(s.url); toast.success("Copied!"); }}
                  className="p-1.5 rounded hover:bg-white/10" style={{color:"var(--cyan)"}}>
                  <Link size={12} />
                </button>
                <button onClick={() => setQrSub(qrSub?.id === s.id ? null : s)}
                  className="p-1.5 rounded hover:bg-white/10" style={{color:"var(--success)"}}>
                  <QrCode size={12} />
                </button>
                <button onClick={() => del(s.id)} className="p-1.5 rounded hover:bg-white/10" style={{color:"var(--danger)"}}>
                  <Trash2 size={12} />
                </button>
              </div>
            </div>
            <div className="text-xs mono truncate" style={{color:"var(--text-muted)"}}>{s.url}</div>
            {qrSub?.id === s.id && (
              <div className="flex justify-center mt-3 p-3 rounded" style={{background:"#fff"}}>
                <QRCode value={s.url} size={140} />
              </div>
            )}
          </div>
        ))}
        {!subs.length && (
          <div className="text-center py-6 text-sm" style={{color:"var(--text-muted)"}}>
            No subscriptions yet
          </div>
        )}
      </div>
    </Modal>
  );
}

function TrafficBar({ used, limit }) {
  if (limit === 0) return <span className="text-xs" style={{color:"var(--success)"}}>Unlimited</span>;
  const pct = Math.min((used / limit) * 100, 100);
  const color = pct > 90 ? "var(--danger)" : pct > 70 ? "var(--warn)" : "var(--success)";
  return (
    <div className="w-24">
      <div className="flex justify-between text-xs mb-0.5">
        <span style={{color}}>{used.toFixed(1)}</span>
        <span style={{color:"var(--text-muted)"}}>{limit}GB</span>
      </div>
      <div className="h-1 rounded-full" style={{background:"var(--border)"}}>
        <div className="h-full rounded-full" style={{width:`${pct}%`,background:color}} />
      </div>
    </div>
  );
}

export default function Users() {
  const [users, setUsers]   = useState([]);
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

  const toggleActive = async (user) => {
    try {
      await usersApi.update(user.id, { is_active: !user.is_active });
      load();
    } catch { toast.error("Update failed"); }
  };

  const resetTraffic = async (id) => {
    try { await usersApi.resetTraffic(id); toast.success("Traffic reset"); load(); }
    catch { toast.error("Reset failed"); }
  };

  return (
    <div className="p-6 max-w-6xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-bold mono" style={{color:"var(--cyan)"}}>Users</h1>
          <p className="text-xs mt-1" style={{color:"var(--text-muted)"}}>{users.length} accounts</p>
        </div>
        <button onClick={() => setAddOpen(true)}
          className="flex items-center gap-2 px-3 py-1.5 rounded text-sm font-semibold hover:opacity-90"
          style={{background:"linear-gradient(135deg,var(--cyan),var(--violet))",color:"#fff"}}>
          <Plus size={14} /> Create User
        </button>
      </div>

      {loading ? (
        <div className="text-center py-16" style={{color:"var(--text-muted)"}}>Loading...</div>
      ) : (
        <div className="rounded-lg box-glow overflow-hidden" style={{background:"var(--card)"}}>
          <table className="w-full text-sm">
            <thead>
              <tr style={{borderBottom:"1px solid var(--border)"}}>
                {["User","Status","Traffic","Expires","Subscriptions","Actions"].map((h) => (
                  <th key={h} className="px-4 py-3 text-left text-xs uppercase tracking-widest"
                      style={{color:"var(--text-muted)"}}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {users.map((u) => (
                <tr key={u.id} className="border-b transition-colors hover:bg-white/5"
                    style={{borderColor:"var(--border)"}}>
                  <td className="px-4 py-3">
                    <div className="font-medium">{u.username}</div>
                    {u.email && <div className="text-xs" style={{color:"var(--text-muted)"}}>{u.email}</div>}
                    {u.is_admin && (
                      <span className="text-xs px-1.5 rounded" style={{background:"var(--violet)20",color:"var(--violet)"}}>
                        admin
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-1.5">
                      <span className={`dot-${u.is_active && !u.is_expired ? "online" : "offline"}`} />
                      <span className="text-xs" style={{color:u.is_active && !u.is_expired ? "var(--success)" : "var(--danger)"}}>
                        {!u.is_active ? "Disabled" : u.is_expired ? "Expired" : "Active"}
                      </span>
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <TrafficBar used={u.traffic_used_gb} limit={u.traffic_limit_gb} />
                  </td>
                  <td className="px-4 py-3 text-xs mono" style={{color:"var(--text-muted)"}}>
                    {u.expire_at ? dayjs(u.expire_at).format("YYYY-MM-DD") : "Never"}
                  </td>
                  <td className="px-4 py-3">
                    <button onClick={() => setSubUser(u)}
                      className="flex items-center gap-1 text-xs px-2 py-1 rounded hover:opacity-80"
                      style={{background:"var(--cyan)20",color:"var(--cyan)"}}>
                      <Link size={11} /> Sub
                    </button>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-1">
                      <button onClick={() => toggleActive(u)}
                        className="p-1.5 rounded hover:bg-white/10"
                        title={u.is_active ? "Disable" : "Enable"}
                        style={{color: u.is_active ? "var(--warn)" : "var(--success)"}}>
                        {u.is_active ? <Ban size={13} /> : <CheckCircle2 size={13} />}
                      </button>
                      <button onClick={() => resetTraffic(u.id)}
                        className="p-1.5 rounded hover:bg-white/10" title="Reset traffic"
                        style={{color:"var(--cyan)"}}>
                        <RefreshCw size={13} />
                      </button>
                      <button onClick={() => del(u.id)}
                        className="p-1.5 rounded hover:bg-white/10" title="Delete"
                        style={{color:"var(--danger)"}}>
                        <Trash2 size={13} />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {!users.length && (
            <div className="text-center py-12 text-sm" style={{color:"var(--text-muted)"}}>No users</div>
          )}
        </div>
      )}

      {addOpen  && <AddUserModal onClose={() => setAddOpen(false)} onCreated={load} />}
      {subUser  && <SubModal user={subUser} onClose={() => setSubUser(null)} />}
    </div>
  );
}
