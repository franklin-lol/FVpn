import React, { useEffect, useState, useCallback } from "react";
import { Server, Plus, Trash2, Zap, RefreshCw, CheckCircle2, XCircle, Clock } from "lucide-react";
import { nodesApi, protocolsApi } from "../utils/api";
import toast from "react-hot-toast";

const PROTOCOLS = ["hysteria2","shadowsocks","shadowtls","vless","trojan","tuic","wireguard"];
const DEFAULT_PORTS = { hysteria2:443, shadowsocks:8443, shadowtls:443, vless:443, trojan:443, tuic:443, wireguard:51820 };
const PROTO_COLORS = { hysteria2:"#00d4ff", shadowsocks:"#f59e0b", shadowtls:"#22c55e", vless:"#7c3aed", trojan:"#ef4444", tuic:"#3b82f6", wireguard:"#06b6d4", ssh:"#64748b" };

function Sk({ h=14, w="100%" }) {
  return <div className="skeleton" style={{ height:h, width:w, borderRadius:4 }} />;
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

function StatusBadge({ status, latency }) {
  if (status === "online")  return <span className="badge badge-green"><span className="dot dot-online" style={{width:5,height:5}}/>{latency ? `${latency.toFixed(0)}ms` : "online"}</span>;
  if (status === "offline") return <span className="badge badge-red">offline</span>;
  return <span className="badge" style={{ background:"rgba(100,116,139,.1)", color:"var(--text-muted)", border:"1px solid var(--border)" }}>unknown</span>;
}

function AddNodeModal({ onClose, onCreated }) {
  const [form, setForm] = useState({ name:"", host:"", ssh_port:22, ssh_user:"root", ssh_key:"", group:"" });
  const [busy, setBusy] = useState(false);
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  const submit = async () => {
    if (!form.name || !form.host) { toast.error("Name and host are required"); return; }
    setBusy(true);
    try {
      await nodesApi.create({ ...form, ssh_port: Number(form.ssh_port) });
      toast.success("Node added");
      onCreated(); onClose();
    } catch (e) { toast.error(e.response?.data?.detail || "Error"); }
    finally { setBusy(false); }
  };

  return (
    <Modal title="Add Node" onClose={onClose}>
      <Field label="Display Name">
        <input className="input" value={form.name} onChange={set("name")} placeholder="Frankfurt-01" autoFocus />
      </Field>
      <Field label="Host / IP">
        <input className="input" value={form.host} onChange={set("host")} placeholder="1.2.3.4" />
      </Field>
      <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr", gap:12 }}>
        <Field label="SSH Port"><input className="input" type="number" value={form.ssh_port} onChange={set("ssh_port")} /></Field>
        <Field label="SSH User"><input className="input" value={form.ssh_user} onChange={set("ssh_user")} /></Field>
      </div>
      <Field label="Group (optional)">
        <input className="input" value={form.group} onChange={set("group")} placeholder="Europe" />
      </Field>
      <Field label="SSH Private Key (PEM)">
        <textarea className="input" value={form.ssh_key} onChange={set("ssh_key")} placeholder="-----BEGIN OPENSSH PRIVATE KEY-----&#10;...&#10;-----END OPENSSH PRIVATE KEY-----" />
      </Field>
      <button className="btn btn-primary" style={{ width:"100%", justifyContent:"center", marginTop:4 }} onClick={submit} disabled={busy}>
        {busy ? <><div className="btn-spinner"/>Adding…</> : "Add Node"}
      </button>
    </Modal>
  );
}

function AutoSetupModal({ node, onClose, onDone }) {
  const [protocol, setProtocol] = useState("hysteria2");
  const [port,     setPort]     = useState(443);
  const [busy,     setBusy]     = useState(false);

  useEffect(() => { setPort(DEFAULT_PORTS[protocol] || 443); }, [protocol]);

  const submit = async () => {
    setBusy(true);
    try {
      await nodesApi.autoSetup(node.id, { protocol, port: Number(port) });
      toast.success(`Installing ${protocol} on ${node.name}…`);
      onDone(); onClose();
    } catch (e) { toast.error(e.response?.data?.detail || "Setup failed"); }
    finally { setBusy(false); }
  };

  return (
    <Modal title={`Auto Setup — ${node.name}`} onClose={onClose}>
      <p style={{ fontSize:12, color:"var(--text-muted)", marginBottom:16, lineHeight:1.6 }}>
        SSH into <span className="mono" style={{ color:"var(--cyan)" }}>{node.host}</span> and automatically install the selected protocol.
      </p>
      <Field label="Protocol">
        <select className="input select" value={protocol} onChange={(e) => setProtocol(e.target.value)}>
          {PROTOCOLS.map((p) => <option key={p} value={p}>{p}</option>)}
        </select>
      </Field>
      <Field label="Port">
        <input className="input" type="number" value={port} onChange={(e) => setPort(e.target.value)} />
      </Field>
      <button className="btn btn-primary" style={{ width:"100%", justifyContent:"center", marginTop:4 }} onClick={submit} disabled={busy}>
        {busy ? <><div className="btn-spinner"/>Installing…</> : <><Zap size={13}/>Auto Setup</>}
      </button>
    </Modal>
  );
}

function NodeCard({ node, onDelete, onCheck, onSetup }) {
  return (
    <div className="card fade-in" style={{ padding:18 }}>
      <div style={{ display:"flex", alignItems:"flex-start", justifyContent:"space-between", gap:12 }}>
        <div style={{ minWidth:0 }}>
          <div style={{ display:"flex", alignItems:"center", gap:8, marginBottom:4 }}>
            <span style={{ fontWeight:600, fontSize:14 }}>{node.name}</span>
            <StatusBadge status={node.status} latency={node.latency_ms} />
          </div>
          <div className="mono" style={{ fontSize:11, color:"var(--text-muted)" }}>
            {node.host}:{node.ssh_port} · {node.group || "no group"}
          </div>
          {node.protocols?.length > 0 && (
            <div style={{ display:"flex", gap:4, flexWrap:"wrap", marginTop:8 }}>
              {node.protocols.map((p) => (
                <span key={p.id} className="badge badge-violet" style={{ fontSize:10, color: PROTO_COLORS[p.name] || "#a78bfa" }}>
                  {p.name}:{p.port}
                </span>
              ))}
            </div>
          )}
        </div>

        <div style={{ display:"flex", gap:4, flexShrink:0 }}>
          <button className="btn-icon" title="Check latency" onClick={() => onCheck(node.id)} style={{ color:"var(--cyan)" }}>
            <RefreshCw size={13}/>
          </button>
          <button className="btn-icon" title="Auto-install protocol" onClick={() => onSetup(node)} style={{ color:"var(--success)" }}>
            <Zap size={13}/>
          </button>
          <button className="btn-icon" title="Delete" onClick={() => onDelete(node.id)} style={{ color:"var(--danger)" }}>
            <Trash2 size={13}/>
          </button>
        </div>
      </div>
    </div>
  );
}

export default function Nodes() {
  const [nodes,   setNodes]   = useState([]);
  const [loading, setLoading] = useState(true);
  const [addOpen, setAddOpen] = useState(false);
  const [setup,   setSetup]   = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try { const { data } = await nodesApi.list(); setNodes(data); }
    catch { toast.error("Failed to load nodes"); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const del = async (id) => {
    if (!confirm("Delete this node and all its protocols?")) return;
    try { await nodesApi.delete(id); toast.success("Node removed"); load(); }
    catch { toast.error("Delete failed"); }
  };

  const check = async (id) => {
    try {
      const { data } = await nodesApi.check(id);
      const lat = data.latency_ms ? `${data.latency_ms.toFixed(0)}ms` : "";
      toast.success(`${data.status}${lat ? " · "+lat : ""}`);
      load();
    } catch { toast.error("Check failed"); }
  };

  const checkAll = async () => {
    try { await nodesApi.checkAll(); toast.success("Health check started"); setTimeout(load, 3000); }
    catch { toast.error("Failed"); }
  };

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <div className="page-title">Nodes</div>
          <div className="page-sub">{nodes.length} server{nodes.length !== 1 ? "s" : ""}</div>
        </div>
        <div style={{ display:"flex", gap:8 }}>
          <button className="btn btn-ghost btn-sm" onClick={checkAll}>
            <RefreshCw size={12}/>Check All
          </button>
          <button className="btn btn-primary btn-sm" onClick={() => setAddOpen(true)}>
            <Plus size={13}/>Add Node
          </button>
        </div>
      </div>

      {loading ? (
        <div style={{ display:"grid", gap:12 }}>
          {[1,2,3].map((k) => (
            <div key={k} className="card" style={{ padding:18 }}>
              <Sk h={16} w="40%" /><Sk h={11} w="60%" style={{ marginTop:8 }} />
            </div>
          ))}
        </div>
      ) : nodes.length === 0 ? (
        <div className="empty">
          <div className="empty-icon"><Server size={20}/></div>
          <h3>No nodes yet</h3>
          <p>Add your first server to get started</p>
          <button className="btn btn-primary btn-sm" onClick={() => setAddOpen(true)} style={{ marginTop:4 }}>
            <Plus size={13}/>Add Node
          </button>
        </div>
      ) : (
        <div style={{ display:"grid", gap:10 }}>
          {nodes.map((n) => (
            <NodeCard key={n.id} node={n}
              onDelete={del} onCheck={check} onSetup={setSetup} />
          ))}
        </div>
      )}

      {addOpen && <AddNodeModal onClose={() => setAddOpen(false)} onCreated={load}/>}
      {setup   && <AutoSetupModal node={setup} onClose={() => setSetup(null)} onDone={load}/>}
    </div>
  );
}
