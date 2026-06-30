import React, { useEffect, useState, useCallback } from "react";
import { Plus, Trash2, Eye, Copy, Check } from "lucide-react";
import { protocolsApi, nodesApi } from "../utils/api";
import toast from "react-hot-toast";

const PROTO_COLORS = {
  hysteria2:"#00d4ff", shadowsocks:"#f59e0b", shadowtls:"#22c55e",
  vless:"#7c3aed", trojan:"#ef4444", tuic:"#3b82f6", wireguard:"#06b6d4", ssh:"#64748b",
};

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

function CopyButton({ text }) {
  const [done, setDone] = useState(false);
  const copy = () => {
    navigator.clipboard.writeText(text);
    setDone(true);
    setTimeout(() => setDone(false), 1500);
  };
  return (
    <button className="btn-icon" onClick={copy} title="Copy" style={{ color: done?"var(--success)":"var(--cyan)" }}>
      {done ? <Check size={12}/> : <Copy size={12}/>}
    </button>
  );
}

function AddProtoModal({ nodes, supported, onClose, onCreated }) {
  const [form, setForm] = useState({ node_id:"", name:"hysteria2", port:443, config:{} });
  const [busy, setBusy] = useState(false);
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  const submit = async () => {
    if (!form.node_id) { toast.error("Select a node"); return; }
    setBusy(true);
    try {
      await protocolsApi.create({ ...form, node_id:Number(form.node_id), port:Number(form.port) });
      toast.success("Protocol added — default parameters auto-generated");
      onCreated(); onClose();
    } catch (e) { toast.error(e.response?.data?.detail || "Error"); }
    finally { setBusy(false); }
  };

  return (
    <Modal title="Add Protocol" onClose={onClose}>
      <Field label="Node">
        <select className="input select" value={form.node_id} onChange={set("node_id")} autoFocus>
          <option value="">Select node…</option>
          {nodes.map((n) => <option key={n.id} value={n.id}>{n.name} ({n.host})</option>)}
        </select>
      </Field>
      <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr", gap:12 }}>
        <Field label="Protocol">
          <select className="input select" value={form.name} onChange={set("name")}>
            {supported.map((p) => <option key={p.name} value={p.name}>{p.name}</option>)}
          </select>
        </Field>
        <Field label="Port">
          <input className="input" type="number" value={form.port} onChange={set("port")} />
        </Field>
      </div>
      <p style={{ fontSize:11, color:"var(--text-muted)", marginBottom:14, lineHeight:1.6 }}>
        Passwords, UUIDs, and keys are auto-generated. Edit individual values after creation if needed.
      </p>
      <button className="btn btn-primary" style={{ width:"100%", justifyContent:"center" }} onClick={submit} disabled={busy}>
        {busy ? <><div className="btn-spinner"/>Adding…</> : "Add Protocol"}
      </button>
    </Modal>
  );
}

function PreviewModal({ onClose }) {
  const [form, setForm] = useState({ protocol:"hysteria2", host:"1.2.3.4", port:443, format:"singbox", config:{} });
  const [result, setResult] = useState(null);
  const [busy,   setBusy]   = useState(false);
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  const run = async () => {
    setBusy(true);
    try {
      const { data } = await protocolsApi.preview({ ...form, port:Number(form.port) });
      setResult(data.config);
    } catch (e) { toast.error(e.response?.data?.detail || "Preview failed"); }
    finally { setBusy(false); }
  };

  return (
    <Modal title="Config Preview" onClose={onClose} wide>
      <div style={{ display:"grid", gridTemplateColumns:"repeat(3,1fr)", gap:12 }}>
        <Field label="Protocol">
          <select className="input select" value={form.protocol} onChange={set("protocol")}>
            {["hysteria2","shadowsocks","vless","trojan","tuic","wireguard"].map((p)=><option key={p} value={p}>{p}</option>)}
          </select>
        </Field>
        <Field label="Host">
          <input className="input" value={form.host} onChange={set("host")} placeholder="1.2.3.4" />
        </Field>
        <Field label="Port">
          <input className="input" type="number" value={form.port} onChange={set("port")} />
        </Field>
      </div>
      <Field label="Output Format">
        <select className="input select" value={form.format} onChange={set("format")}>
          {["singbox","clash","hiddify","shadowrocket","v2rayng","base64"].map((f)=><option key={f} value={f}>{f}</option>)}
        </select>
      </Field>
      <button className="btn btn-ghost" style={{ width:"100%", justifyContent:"center", marginBottom:12 }} onClick={run} disabled={busy}>
        {busy ? <><div className="btn-spinner"/>Generating…</> : <><Eye size={13}/>Generate Preview</>}
      </button>
      {result && (
        <div style={{ position:"relative" }}>
          <pre style={{ background:"var(--surface)", border:"1px solid var(--border)", borderRadius:8,
            padding:12, fontSize:11, overflow:"auto", maxHeight:260, fontFamily:"JetBrains Mono,monospace",
            color:"var(--text)", lineHeight:1.5 }}>
            {result.length > 2000 ? result.slice(0,2000)+"…" : result}
          </pre>
          <div style={{ position:"absolute", top:8, right:8 }}>
            <CopyButton text={result}/>
          </div>
        </div>
      )}
    </Modal>
  );
}

function ProtoCard({ proto, nodeMap, onDelete }) {
  const color = PROTO_COLORS[proto.name] || "var(--text-muted)";
  const node  = nodeMap[proto.node_id];
  const secret = ["private_key","ssh_key","preshared_key"];

  return (
    <div className="card fade-in" style={{ padding:18 }}>
      <div style={{ display:"flex", alignItems:"center", justifyContent:"space-between", marginBottom:12 }}>
        <div style={{ display:"flex", alignItems:"center", gap:8 }}>
          <div style={{ width:10, height:10, borderRadius:"50%", background:color, boxShadow:`0 0 6px ${color}` }}/>
          <span className="mono" style={{ fontWeight:700, fontSize:14, color }}>{proto.name}</span>
          <span style={{ fontSize:12, color:"var(--text-muted)" }}>:{proto.port}</span>
        </div>
        <div style={{ display:"flex", gap:4, alignItems:"center" }}>
          <span className={`badge badge-${proto.is_active?"green":"red"}`} style={{ fontSize:10 }}>
            {proto.is_active?"active":"disabled"}
          </span>
          <button className="btn-icon" onClick={() => onDelete(proto.id)} style={{ color:"var(--danger)" }}>
            <Trash2 size={12}/>
          </button>
        </div>
      </div>

      {node && (
        <div style={{ fontSize:11, color:"var(--text-muted)", background:"var(--surface)",
          border:"1px solid var(--border)", borderRadius:6, padding:"5px 8px", marginBottom:10,
          fontFamily:"JetBrains Mono,monospace" }}>
          → {node.name} <span style={{ opacity:.5 }}>({node.host})</span>
        </div>
      )}

      <div style={{ display:"flex", flexDirection:"column", gap:3 }}>
        {Object.entries(proto.config)
          .filter(([k]) => !secret.includes(k))
          .slice(0, 6)
          .map(([k, v]) => (
            <div key={k} style={{ display:"flex", justifyContent:"space-between", gap:8 }}>
              <span style={{ fontSize:11, color:"var(--text-muted)", flexShrink:0 }}>{k}</span>
              <span className="mono truncate" style={{ fontSize:11, color:"var(--text)", maxWidth:160 }} title={String(v)}>
                {String(v).length > 20 ? String(v).slice(0,20)+"…" : String(v)}
              </span>
            </div>
          ))}
      </div>
    </div>
  );
}

export default function Protocols() {
  const [protos,    setProtos]    = useState([]);
  const [nodes,     setNodes]     = useState([]);
  const [supported, setSupported] = useState([]);
  const [loading,   setLoading]   = useState(true);
  const [addOpen,   setAddOpen]   = useState(false);
  const [prevOpen,  setPrevOpen]  = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [{ data:p }, { data:n }, { data:s }] = await Promise.all([
        protocolsApi.list(), nodesApi.list(), protocolsApi.supported(),
      ]);
      setProtos(p); setNodes(n); setSupported(s.protocols || []);
    } catch { toast.error("Failed to load"); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const del = async (id) => {
    try { await protocolsApi.delete(id); toast.success("Protocol removed"); load(); }
    catch { toast.error("Delete failed"); }
  };

  const nodeMap = Object.fromEntries(nodes.map((n) => [n.id, n]));

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <div className="page-title">Protocols</div>
          <div className="page-sub">{protos.length} configured</div>
        </div>
        <div style={{ display:"flex", gap:8 }}>
          <button className="btn btn-ghost btn-sm" onClick={() => setPrevOpen(true)}>
            <Eye size={12}/>Preview Config
          </button>
          <button className="btn btn-primary btn-sm" onClick={() => setAddOpen(true)}>
            <Plus size={13}/>Add Protocol
          </button>
        </div>
      </div>

      {loading ? (
        <div style={{ display:"grid", gridTemplateColumns:"repeat(auto-fill,minmax(260px,1fr))", gap:12 }}>
          {[1,2,3].map((k) => (
            <div key={k} className="card" style={{ padding:18 }}>
              <Sk h={14} w="50%"/><Sk h={10} w="70%" style={{ marginTop:8 }}/><Sk h={10} w="60%" style={{ marginTop:6 }}/>
            </div>
          ))}
        </div>
      ) : protos.length === 0 ? (
        <div className="empty">
          <div className="empty-icon"><span style={{ fontSize:20 }}>🔒</span></div>
          <h3>No protocols configured</h3>
          <p>Add a node first, then attach proxy protocols to it</p>
          <button className="btn btn-primary btn-sm" onClick={() => setAddOpen(true)} style={{ marginTop:8 }}>
            <Plus size={13}/>Add Protocol
          </button>
        </div>
      ) : (
        <div style={{ display:"grid", gridTemplateColumns:"repeat(auto-fill,minmax(260px,1fr))", gap:12 }}>
          {protos.map((p) => (
            <ProtoCard key={p.id} proto={p} nodeMap={nodeMap} onDelete={del}/>
          ))}
        </div>
      )}

      {addOpen  && <AddProtoModal nodes={nodes} supported={supported} onClose={() => setAddOpen(false)} onCreated={load}/>}
      {prevOpen && <PreviewModal onClose={() => setPrevOpen(false)}/>}
    </div>
  );
}
