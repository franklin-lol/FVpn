import React, { useEffect, useState, useCallback } from "react";
import { Plus, Trash2, Eye, Copy } from "lucide-react";
import { protocolsApi, nodesApi } from "../utils/api";
import toast from "react-hot-toast";

const FORMATS = ["singbox","clash","hiddify","shadowrocket","v2rayng","base64"];

function Modal({ title, onClose, children }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" style={{background:"rgba(0,0,0,0.75)"}}>
      <div className="w-full max-w-2xl rounded-xl p-6 box-glow" style={{background:"var(--card)"}}>
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

const PROTO_COLORS = {
  hysteria2:   "#00d4ff",
  shadowsocks: "#f59e0b",
  shadowtls:   "#10b981",
  vless:       "#7c3aed",
  trojan:      "#ef4444",
  tuic:        "#3b82f6",
  wireguard:   "#06b6d4",
  ssh:         "#64748b",
};

function AddProtoModal({ nodes, onClose, onCreated }) {
  const [supported, setSupported] = useState([]);
  const [form, setForm] = useState({ node_id:"", name:"hysteria2", port:443, config:{} });
  const [busy, setBusy] = useState(false);
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  useEffect(() => {
    protocolsApi.supported().then(({ data }) => setSupported(data.protocols));
  }, []);

  const submit = async () => {
    if (!form.node_id) return toast.error("Select a node");
    setBusy(true);
    try {
      await protocolsApi.create({ ...form, node_id: Number(form.node_id), port: Number(form.port) });
      toast.success("Protocol added");
      onCreated(); onClose();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Error");
    } finally { setBusy(false); }
  };

  return (
    <Modal title="Add Protocol" onClose={onClose}>
      <Field label="Node">
        <select className={inp} style={inpStyle} value={form.node_id} onChange={set("node_id")}>
          <option value="">Select node…</option>
          {nodes.map((n) => <option key={n.id} value={n.id}>{n.name} ({n.host})</option>)}
        </select>
      </Field>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Protocol">
          <select className={inp} style={inpStyle} value={form.name} onChange={set("name")}>
            {supported.map((p) => <option key={p.name} value={p.name}>{p.name}</option>)}
          </select>
        </Field>
        <Field label="Port">
          <input className={inp} style={inpStyle} type="number" value={form.port} onChange={set("port")} />
        </Field>
      </div>
      <p className="text-xs mb-4" style={{color:"var(--text-muted)"}}>
        Default parameters are auto-generated. You can override them after creation.
      </p>
      <button onClick={submit} disabled={busy}
        className="w-full py-2 rounded font-semibold text-sm hover:opacity-90"
        style={{background:"linear-gradient(135deg,var(--cyan),var(--violet))",color:"#fff"}}>
        {busy ? "Adding..." : "Add Protocol"}
      </button>
    </Modal>
  );
}

function PreviewModal({ onClose }) {
  const [nodes, setNodes] = useState([]);
  const [form, setForm] = useState({ protocol:"hysteria2", host:"1.2.3.4", port:443, format:"singbox", config:{} });
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  useEffect(() => {
    nodesApi.list().then(({ data }) => setNodes(data));
  }, []);

  const preview = async () => {
    setBusy(true);
    try {
      const { data } = await protocolsApi.preview(form);
      setResult(data.config);
    } catch (e) {
      toast.error(e.response?.data?.detail || "Preview failed");
    } finally { setBusy(false); }
  };

  return (
    <Modal title="Config Preview" onClose={onClose}>
      <div className="grid grid-cols-3 gap-3 mb-3">
        <Field label="Protocol">
          <select className={inp} style={inpStyle} value={form.protocol} onChange={set("protocol")}>
            {["hysteria2","shadowsocks","vless","trojan","tuic","wireguard"].map((p) =>
              <option key={p} value={p}>{p}</option>)}
          </select>
        </Field>
        <Field label="Host">
          <input className={inp} style={inpStyle} value={form.host} onChange={set("host")} />
        </Field>
        <Field label="Port">
          <input className={inp} style={inpStyle} type="number" value={form.port} onChange={set("port")} />
        </Field>
      </div>
      <Field label="Output Format">
        <select className={inp} style={inpStyle} value={form.format} onChange={set("format")}>
          {FORMATS.map((f) => <option key={f} value={f}>{f}</option>)}
        </select>
      </Field>
      <button onClick={preview} disabled={busy}
        className="w-full py-2 rounded text-sm font-semibold mb-4 hover:opacity-90"
        style={{background:"var(--surface)",border:"1px solid var(--cyan)",color:"var(--cyan)"}}>
        {busy ? "Generating..." : "Generate Preview"}
      </button>
      {result && (
        <div className="relative">
          <pre className="p-3 rounded text-xs overflow-auto max-h-64 mono"
               style={{background:"var(--surface)",color:"var(--text)",border:"1px solid var(--border)"}}>
            {result.length > 2000 ? result.slice(0,2000)+"..." : result}
          </pre>
          <button
            onClick={() => { navigator.clipboard.writeText(result); toast.success("Copied!"); }}
            className="absolute top-2 right-2 p-1.5 rounded hover:bg-white/20"
            style={{color:"var(--cyan)"}}>
            <Copy size={12} />
          </button>
        </div>
      )}
    </Modal>
  );
}

export default function Protocols() {
  const [protocols, setProtocols] = useState([]);
  const [nodes,     setNodes]     = useState([]);
  const [loading,   setLoading]   = useState(true);
  const [addOpen,   setAddOpen]   = useState(false);
  const [previewOpen, setPreviewOpen] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [{ data: protos }, { data: nds }] = await Promise.all([
        protocolsApi.list(),
        nodesApi.list(),
      ]);
      setProtocols(protos);
      setNodes(nds);
    } catch { toast.error("Load failed"); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const del = async (id) => {
    try { await protocolsApi.delete(id); toast.success("Protocol removed"); load(); }
    catch { toast.error("Delete failed"); }
  };

  const nodeMap = Object.fromEntries(nodes.map((n) => [n.id, n]));

  return (
    <div className="p-6 max-w-6xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-bold mono" style={{color:"var(--cyan)"}}>Protocols</h1>
          <p className="text-xs mt-1" style={{color:"var(--text-muted)"}}>{protocols.length} configured</p>
        </div>
        <div className="flex gap-2">
          <button onClick={() => setPreviewOpen(true)}
            className="flex items-center gap-2 px-3 py-1.5 rounded text-sm transition-colors hover:bg-white/10"
            style={{border:"1px solid var(--border)",color:"var(--cyan)"}}>
            <Eye size={13} /> Preview Config
          </button>
          <button onClick={() => setAddOpen(true)}
            className="flex items-center gap-2 px-3 py-1.5 rounded text-sm font-semibold hover:opacity-90"
            style={{background:"linear-gradient(135deg,var(--cyan),var(--violet))",color:"#fff"}}>
            <Plus size={14} /> Add Protocol
          </button>
        </div>
      </div>

      {loading ? (
        <div className="text-center py-16" style={{color:"var(--text-muted)"}}>Loading...</div>
      ) : protocols.length === 0 ? (
        <div className="text-center py-16">
          <p style={{color:"var(--text-muted)"}}>No protocols configured yet.</p>
          <p className="text-xs mt-2" style={{color:"var(--text-dim)"}}>Add a node first, then attach protocols to it.</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {protocols.map((p) => {
            const color = PROTO_COLORS[p.name] || "var(--text-muted)";
            const node  = nodeMap[p.node_id];
            return (
              <div key={p.id} className="rounded-lg p-4 box-glow" style={{background:"var(--card)"}}>
                <div className="flex items-center justify-between mb-3">
                  <div className="flex items-center gap-2">
                    <div className="w-2 h-2 rounded-full" style={{background:color}} />
                    <span className="font-bold mono text-sm" style={{color}}>{p.name}</span>
                    <span className="text-xs" style={{color:"var(--text-muted)"}}>:{p.port}</span>
                  </div>
                  <div className="flex gap-1">
                    <span className={`dot-${p.is_active ? "online" : "offline"}`} />
                    <button onClick={() => del(p.id)}
                      className="p-1 rounded hover:bg-white/10" style={{color:"var(--danger)"}}>
                      <Trash2 size={12} />
                    </button>
                  </div>
                </div>

                {node && (
                  <div className="text-xs mb-3 px-2 py-1 rounded" style={{background:"var(--surface)",color:"var(--text-muted)"}}>
                    → {node.name} ({node.host})
                  </div>
                )}

                <div className="space-y-1">
                  {Object.entries(p.config)
                    .filter(([k]) => !["private_key","ssh_key"].includes(k))
                    .slice(0, 5)
                    .map(([k, v]) => (
                      <div key={k} className="flex justify-between text-xs">
                        <span style={{color:"var(--text-muted)"}}>{k}</span>
                        <span className="mono truncate ml-2" style={{color:"var(--text)",maxWidth:120}} title={String(v)}>
                          {String(v).length > 18 ? String(v).slice(0,18)+"…" : String(v)}
                        </span>
                      </div>
                    ))
                  }
                </div>
              </div>
            );
          })}
        </div>
      )}

      {addOpen     && <AddProtoModal  nodes={nodes} onClose={() => setAddOpen(false)}   onCreated={load} />}
      {previewOpen && <PreviewModal               onClose={() => setPreviewOpen(false)} />}
    </div>
  );
}
