import React, { useEffect, useState, useCallback } from "react";
import { Server, Plus, Trash2, Zap, RefreshCw, CheckCircle2, XCircle, Clock } from "lucide-react";
import { nodesApi, protocolsApi } from "../utils/api";
import toast from "react-hot-toast";

const PROTOCOLS = ["hysteria2","shadowsocks","shadowtls","vless","trojan","tuic","wireguard"];
const DEFAULT_PORTS = { hysteria2:443,shadowsocks:8443,shadowtls:443,vless:443,trojan:443,tuic:443,wireguard:51820 };

function StatusIcon({ status }) {
  if (status === "online")  return <CheckCircle2 size={14} style={{color:"var(--success)"}} />;
  if (status === "offline") return <XCircle size={14} style={{color:"var(--danger)"}} />;
  return <Clock size={14} style={{color:"var(--text-muted)"}} />;
}

function Modal({ title, onClose, children }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4"
         style={{background:"rgba(0,0,0,0.7)"}}>
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

function Field({ label, children }) {
  return (
    <div className="mb-3">
      <label className="block text-xs mb-1" style={{color:"var(--text-muted)"}}>{label}</label>
      {children}
    </div>
  );
}

const inp = "w-full px-3 py-2 rounded text-sm mono outline-none focus:ring-1";
const inpStyle = { background:"var(--surface)", border:"1px solid var(--border)", color:"var(--text)", "--tw-ring-color":"var(--cyan)" };

function AddNodeModal({ onClose, onCreated }) {
  const [form, setForm] = useState({ name:"", host:"", ssh_port:22, ssh_user:"root", ssh_key:"", group:"" });
  const [busy, setBusy] = useState(false);
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  const submit = async () => {
    if (!form.name || !form.host) return toast.error("Name and host required");
    setBusy(true);
    try {
      await nodesApi.create(form);
      toast.success("Node added");
      onCreated();
      onClose();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Error");
    } finally { setBusy(false); }
  };

  return (
    <Modal title="Add Node" onClose={onClose}>
      <Field label="Display Name">
        <input className={inp} style={inpStyle} value={form.name} onChange={set("name")} placeholder="Frankfurt-01" />
      </Field>
      <Field label="Host / IP">
        <input className={inp} style={inpStyle} value={form.host} onChange={set("host")} placeholder="1.2.3.4" />
      </Field>
      <div className="grid grid-cols-2 gap-3">
        <Field label="SSH Port">
          <input className={inp} style={inpStyle} type="number" value={form.ssh_port} onChange={set("ssh_port")} />
        </Field>
        <Field label="SSH User">
          <input className={inp} style={inpStyle} value={form.ssh_user} onChange={set("ssh_user")} />
        </Field>
      </div>
      <Field label="Group (optional)">
        <input className={inp} style={inpStyle} value={form.group} onChange={set("group")} placeholder="Europe" />
      </Field>
      <Field label="SSH Private Key (PEM)">
        <textarea className={inp} style={{...inpStyle, minHeight:80, resize:"vertical"}}
          value={form.ssh_key} onChange={set("ssh_key")} placeholder="-----BEGIN OPENSSH PRIVATE KEY-----" />
      </Field>
      <button onClick={submit} disabled={busy}
        className="w-full mt-2 py-2 rounded font-semibold text-sm transition-all hover:opacity-90"
        style={{background:"linear-gradient(135deg,var(--cyan),var(--violet))",color:"#fff"}}>
        {busy ? "Adding..." : "Add Node"}
      </button>
    </Modal>
  );
}

function AutoSetupModal({ node, onClose, onDone }) {
  const [protocol, setProtocol] = useState("hysteria2");
  const [port, setPort] = useState(443);
  const [busy, setBusy] = useState(false);

  useEffect(() => { setPort(DEFAULT_PORTS[protocol] || 443); }, [protocol]);

  const submit = async () => {
    setBusy(true);
    try {
      await nodesApi.autoSetup(node.id, { protocol, port });
      toast.success(`Auto-setup '${protocol}' started on ${node.name}`);
      onDone();
      onClose();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Setup failed");
    } finally { setBusy(false); }
  };

  return (
    <Modal title={`Auto Setup — ${node.name}`} onClose={onClose}>
      <p className="text-xs mb-4" style={{color:"var(--text-muted)"}}>
        SSH into <span className="mono" style={{color:"var(--cyan)"}}>{node.host}</span> and install the selected protocol automatically.
      </p>
      <Field label="Protocol">
        <select className={inp} style={inpStyle} value={protocol} onChange={(e) => setProtocol(e.target.value)}>
          {PROTOCOLS.map((p) => <option key={p} value={p}>{p}</option>)}
        </select>
      </Field>
      <Field label="Port">
        <input className={inp} style={inpStyle} type="number" value={port}
               onChange={(e) => setPort(Number(e.target.value))} />
      </Field>
      <button onClick={submit} disabled={busy}
        className="w-full mt-2 py-2 rounded font-semibold text-sm transition-all hover:opacity-90 flex items-center justify-center gap-2"
        style={{background:"linear-gradient(135deg,#10b981,var(--cyan))",color:"#fff"}}>
        <Zap size={14} />
        {busy ? "Installing..." : "Auto Setup"}
      </button>
    </Modal>
  );
}

export default function Nodes() {
  const [nodes,   setNodes]   = useState([]);
  const [loading, setLoading] = useState(true);
  const [addOpen, setAddOpen] = useState(false);
  const [setupNode, setSetupNode] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await nodesApi.list();
      setNodes(data);
    } catch { toast.error("Failed to load nodes"); }
    finally   { setLoading(false); }
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
      toast.success(`${data.status} · ${data.latency_ms ? data.latency_ms.toFixed(0)+"ms" : "N/A"}`);
      load();
    } catch { toast.error("Check failed"); }
  };

  return (
    <div className="p-6 max-w-6xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-bold mono" style={{color:"var(--cyan)"}}>Nodes</h1>
          <p className="text-xs mt-1" style={{color:"var(--text-muted)"}}>
            {nodes.length} server{nodes.length !== 1 ? "s" : ""} registered
          </p>
        </div>
        <div className="flex gap-2">
          <button onClick={() => nodesApi.checkAll().then(load)}
            className="flex items-center gap-2 px-3 py-1.5 rounded text-xs transition-colors hover:bg-white/10"
            style={{border:"1px solid var(--border)",color:"var(--text-muted)"}}>
            <RefreshCw size={12} /> Check All
          </button>
          <button onClick={() => setAddOpen(true)}
            className="flex items-center gap-2 px-3 py-1.5 rounded text-sm font-semibold transition-all hover:opacity-90"
            style={{background:"linear-gradient(135deg,var(--cyan),var(--violet))",color:"#fff"}}>
            <Plus size={14} /> Add Node
          </button>
        </div>
      </div>

      {loading ? (
        <div className="text-center py-16" style={{color:"var(--text-muted)"}}>Loading...</div>
      ) : nodes.length === 0 ? (
        <div className="text-center py-16">
          <Server size={40} style={{color:"var(--border)",margin:"0 auto 12px"}} />
          <p style={{color:"var(--text-muted)"}}>No nodes yet. Add your first server.</p>
        </div>
      ) : (
        <div className="space-y-3">
          {nodes.map((node) => (
            <div key={node.id} className="rounded-lg p-4 box-glow transition-all hover:border-cyan-900/50"
                 style={{background:"var(--card)"}}>
              <div className="flex items-center justify-between gap-4">
                <div className="flex items-center gap-3 flex-1 min-w-0">
                  <StatusIcon status={node.status} />
                  <div className="min-w-0">
                    <div className="font-semibold text-sm">{node.name}</div>
                    <div className="text-xs mono mt-0.5" style={{color:"var(--text-muted)"}}>
                      {node.host}:{node.ssh_port} · {node.group || "no group"}
                    </div>
                  </div>
                  {node.group && (
                    <span className="text-xs px-2 py-0.5 rounded flex-shrink-0"
                          style={{background:"var(--border)",color:"var(--text-muted)"}}>
                      {node.group}
                    </span>
                  )}
                </div>

                <div className="flex items-center gap-4 flex-shrink-0">
                  {node.latency_ms && (
                    <span className="text-xs mono" style={{color:"var(--success)"}}>
                      {node.latency_ms.toFixed(0)}ms
                    </span>
                  )}
                  <div className="flex items-center gap-1">
                    {node.protocols?.map((p) => (
                      <span key={p.id} className="text-xs px-1.5 py-0.5 rounded mono"
                            style={{background:`var(--violet)20`,color:"var(--violet)",border:"1px solid var(--violet)40"}}>
                        {p.name}:{p.port}
                      </span>
                    ))}
                  </div>
                  <button onClick={() => check(node.id)}
                    className="p-1.5 rounded hover:bg-white/10 transition-colors"
                    title="Check latency" style={{color:"var(--cyan)"}}>
                    <RefreshCw size={13} />
                  </button>
                  <button onClick={() => setSetupNode(node)}
                    className="p-1.5 rounded hover:bg-white/10 transition-colors"
                    title="Auto-install protocol" style={{color:"var(--success)"}}>
                    <Zap size={13} />
                  </button>
                  <button onClick={() => del(node.id)}
                    className="p-1.5 rounded hover:bg-white/10 transition-colors"
                    title="Delete" style={{color:"var(--danger)"}}>
                    <Trash2 size={13} />
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {addOpen   && <AddNodeModal    onClose={() => setAddOpen(false)} onCreated={load} />}
      {setupNode && <AutoSetupModal  node={setupNode} onClose={() => setSetupNode(null)} onDone={load} />}
    </div>
  );
}
