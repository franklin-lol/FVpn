import React, { useEffect, useState } from "react";
import { RotateCcw, Shield, Terminal, Download } from "lucide-react";
import api, { statsApi } from "../utils/api";
import toast from "react-hot-toast";

function Sk({ h=14, w="100%" }) {
  return <div className="skeleton" style={{ height:h, width:w, borderRadius:4 }} />;
}

function Card({ title, children }) {
  return (
    <div className="card" style={{ padding:20 }}>
      <div className="label" style={{ marginBottom:16 }}>{title}</div>
      {children}
    </div>
  );
}

function KV({ label, value, accent }) {
  return (
    <div style={{ display:"flex", alignItems:"center", justifyContent:"space-between",
      padding:"7px 0", borderBottom:"1px solid var(--border)" }}>
      <span style={{ fontSize:12, color:"var(--text-muted)" }}>{label}</span>
      <span className="mono truncate" style={{ fontSize:12, color: accent || "var(--text)", maxWidth:220, textAlign:"right" }}>
        {value ?? "—"}
      </span>
    </div>
  );
}

function ServiceRow({ label, onRestart, onStatus }) {
  const [status, setStatus] = useState(null);
  const [busy,   setBusy]   = useState(false);

  const checkStatus = async () => {
    try { const { data } = await onStatus(); setStatus(data.active); }
    catch { setStatus(null); }
  };

  useEffect(() => { checkStatus(); }, []);

  const restart = async () => {
    setBusy(true);
    try {
      await onRestart();
      toast.success(`${label} restarted`);
      setTimeout(checkStatus, 1500);
    } catch (e) {
      toast.error(e.response?.data?.detail || `${label} restart failed`);
    } finally { setBusy(false); }
  };

  return (
    <div style={{ display:"flex", alignItems:"center", justifyContent:"space-between", padding:"8px 0" }}>
      <div style={{ display:"flex", alignItems:"center", gap:8 }}>
        <span className={`dot dot-${status===true?"online":status===false?"offline":"unknown"}`} />
        <span className="mono" style={{ fontSize:13 }}>{label}</span>
      </div>
      <button className="btn btn-ghost btn-sm" onClick={restart} disabled={busy}>
        {busy ? <div className="btn-spinner"/> : <RotateCcw size={11}/>}
        Restart
      </button>
    </div>
  );
}

export default function Settings() {
  const [sysInfo,  setSysInfo]  = useState(null);
  const [versions, setVersions] = useState(null);
  const [certInfo, setCertInfo] = useState(null);
  const [logLines, setLogLines] = useState("");
  const [showLog,  setShowLog]  = useState(false);

  useEffect(() => {
    statsApi.system().then(({ data }) => setSysInfo(data)).catch(() => {});
    api.get("/api/system/version").then(({ data }) => setVersions(data)).catch(() => {});
    api.get("/api/system/cert/status").then(({ data }) => setCertInfo(data)).catch(() => {});
  }, []);

  const viewLogs = async () => {
    try {
      const { data } = await api.get("/api/system/logs/uniproxy?lines=150");
      setLogLines(data);
      setShowLog(true);
    } catch { toast.error("Cannot load logs"); }
  };

  const backup = async () => {
    const id = toast.loading("Running backup…");
    try { await api.post("/api/system/backup"); toast.success("Backup complete", { id }); }
    catch (e) { toast.error(e.response?.data?.detail || "Backup failed", { id }); }
  };

  const renewCert = async () => {
    const id = toast.loading("Renewing certificate…");
    try {
      const { data } = await api.post("/api/system/cert/renew");
      toast[data.code === 0 ? "success" : "error"](data.code === 0 ? "Certificate renewed" : `Failed (code ${data.code})`, { id });
    } catch { toast.error("Renewal failed", { id }); }
  };

  return (
    <div className="page" style={{ maxWidth:1100 }}>
      <div className="page-header">
        <div>
          <div className="page-title">Settings</div>
          <div className="page-sub">System status, services, and maintenance</div>
        </div>
      </div>

      <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr", gap:14 }}>
        {/* Versions */}
        <Card title="Software Versions">
          {versions ? <>
            <KV label="FVpn"      value={versions.fvpn || versions.uniproxy} accent="var(--cyan)" />
            <KV label="Xray-core" value={versions.xray}                      accent="var(--success)" />
            <KV label="Sing-box"  value={versions.sing_box}                  accent="var(--success)" />
          </> : [1,2,3].map((k)=><Sk key={k} h={12} style={{ marginBottom:8 }}/>)}
        </Card>

        {/* System resources */}
        <Card title="System Resources">
          {sysInfo ? <>
            <KV label="CPU Cores"  value={sysInfo.cpu_cores} />
            <KV label="RAM"        value={`${sysInfo.ram.used_gb} / ${sysInfo.ram.total_gb} GB (${sysInfo.ram.pct}%)`}
                accent={sysInfo.ram.pct > 85 ? "var(--danger)" : "var(--success)"} />
            <KV label="Disk"       value={`${sysInfo.disk.used_gb} / ${sysInfo.disk.total_gb} GB (${sysInfo.disk.pct}%)`}
                accent={sysInfo.disk.pct > 85 ? "var(--danger)" : "var(--warn)"} />
            <KV label="Uptime"     value={`${sysInfo.uptime_hours}h`} accent="var(--cyan)" />
            <KV label="Network"    value={`↑${sysInfo.network.sent_gb} GB ↓${sysInfo.network.recv_gb} GB`} />
          </> : [1,2,3,4].map((k)=><Sk key={k} h={12} style={{ marginBottom:8 }}/>)}
        </Card>

        {/* Service control */}
        <Card title="Service Control">
          <ServiceRow label="xray"     onRestart={()=>api.post("/api/system/xray/restart")}     onStatus={()=>api.get("/api/system/xray/status")} />
          <ServiceRow label="sing-box" onRestart={()=>api.post("/api/system/singbox/restart")}  onStatus={()=>api.get("/api/system/singbox/status")} />
          <button className="btn btn-ghost btn-sm" onClick={viewLogs} style={{ width:"100%", justifyContent:"center", marginTop:10 }}>
            <Terminal size={12}/>View Logs
          </button>
        </Card>

        {/* TLS */}
        <Card title="TLS Certificate">
          {certInfo ? <>
            <KV label="Domain" value={certInfo.domain} />
            <KV label="Valid"  value={certInfo.valid ? "Yes" : "No"} accent={certInfo.valid ? "var(--success)" : "var(--danger)"} />
            {certInfo.not_before && <KV label="Issued"  value={certInfo.not_before} />}
            {certInfo.not_after  && <KV label="Expires" value={certInfo.not_after}  />}
            <button className="btn btn-ghost btn-sm" onClick={renewCert} style={{ width:"100%", justifyContent:"center", marginTop:10, color:"var(--cyan)", borderColor:"rgba(0,212,255,.3)" }}>
              <Shield size={12}/>Renew Certificate
            </button>
          </> : [1,2,3].map((k)=><Sk key={k} h={12} style={{ marginBottom:8 }}/>)}
        </Card>

        {/* Backup */}
        <Card title="Backup & Restore">
          <p style={{ fontSize:12, color:"var(--text-muted)", marginBottom:14, lineHeight:1.6 }}>
            Backups include database, protocol configs, and subscription tokens. Auto-backup runs every 6 hours.
          </p>
          <button className="btn btn-primary btn-sm" onClick={backup} style={{ width:"100%", justifyContent:"center" }}>
            <Download size={12}/>Backup Now
          </button>
        </Card>

        {/* About */}
        <Card title="About FVpn">
          <div style={{ fontSize:12, color:"var(--text-muted)", lineHeight:1.7 }}>
            <p>Self-hosted unified proxy management panel.</p>
            <p style={{ marginTop:6 }}>8 protocols: Hysteria2, VLESS-Reality, ShadowTLS, Shadowsocks 2022, Trojan, TUIC, WireGuard, SSH.</p>
            <p style={{ marginTop:6 }}>Config generation: Sing-box, Clash, Hiddify, Shadowrocket, v2rayNG.</p>
            <div style={{ marginTop:12, paddingTop:12, borderTop:"1px solid var(--border)" }}>
              <a href="https://github.com/franklin-lol/FVpn" target="_blank" rel="noopener"
                 className="mono" style={{ color:"var(--cyan)", textDecoration:"none" }}>
                github.com/franklin-lol/FVpn →
              </a>
            </div>
          </div>
        </Card>
      </div>

      {showLog && (
        <div className="overlay" onClick={(e) => e.target===e.currentTarget && setShowLog(false)}>
          <div className="modal modal-wide" style={{ padding:0, overflow:"hidden" }}>
            <div style={{ display:"flex", alignItems:"center", justifyContent:"space-between",
              padding:"14px 20px", borderBottom:"1px solid var(--border)" }}>
              <span className="mono" style={{ fontSize:13, color:"var(--cyan)" }}>/var/log/fvpn.log</span>
              <button className="btn-icon" onClick={() => setShowLog(false)} style={{ border:"none" }}>✕</button>
            </div>
            <pre style={{ padding:20, fontSize:11, overflow:"auto", maxHeight:420,
              fontFamily:"JetBrains Mono,monospace", color:"#a8b4c8", background:"#060a14", margin:0 }}>
              {logLines || "No log output"}
            </pre>
          </div>
        </div>
      )}
    </div>
  );
}
