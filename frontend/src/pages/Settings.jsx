import React, { useEffect, useState } from "react";
import {
  RefreshCw, RotateCcw, HardDrive, Shield, Terminal,
  Activity, Server, Download, Upload
} from "lucide-react";
import api, { statsApi } from "../utils/api";
import toast from "react-hot-toast";

function Card({ title, children }) {
  return (
    <div className="rounded-lg p-5 box-glow" style={{ background: "var(--card)" }}>
      <h2 className="text-xs uppercase tracking-widest mb-4 font-semibold"
          style={{ color: "var(--text-muted)" }}>{title}</h2>
      {children}
    </div>
  );
}

function KV({ label, value, accent }) {
  return (
    <div className="flex items-center justify-between py-1.5 border-b"
         style={{ borderColor: "var(--border)" }}>
      <span className="text-xs" style={{ color: "var(--text-muted)" }}>{label}</span>
      <span className="text-xs mono" style={{ color: accent || "var(--text)" }}>{value ?? "—"}</span>
    </div>
  );
}

function ServiceBtn({ label, onRestart, onStatus }) {
  const [status, setStatus] = useState(null);
  const [busy,   setBusy]   = useState(false);

  const checkStatus = async () => {
    try {
      const { data } = await onStatus();
      setStatus(data.active);
    } catch { setStatus(null); }
  };

  useEffect(() => { checkStatus(); }, []);

  const restart = async () => {
    setBusy(true);
    try {
      await onRestart();
      toast.success(`${label} restarted`);
      await checkStatus();
    } catch { toast.error(`${label} restart failed`); }
    finally { setBusy(false); }
  };

  return (
    <div className="flex items-center justify-between py-2">
      <div className="flex items-center gap-2">
        <span className={`dot-${status === true ? "online" : status === false ? "offline" : "unknown"}`} />
        <span className="text-sm mono">{label}</span>
      </div>
      <button
        onClick={restart} disabled={busy}
        className="flex items-center gap-1.5 px-3 py-1 rounded text-xs transition-colors hover:bg-white/10 disabled:opacity-50"
        style={{ border: "1px solid var(--border)", color: "var(--cyan)" }}
      >
        <RotateCcw size={11} className={busy ? "animate-spin" : ""} />
        Restart
      </button>
    </div>
  );
}

export default function Settings() {
  const [sysInfo, setSysInfo] = useState(null);
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
      const { data } = await api.get("/api/system/logs/uniproxy?lines=100");
      setLogLines(data);
      setShowLog(true);
    } catch { toast.error("Cannot load logs"); }
  };

  const triggerBackup = async () => {
    toast.loading("Running backup...");
    try {
      await api.post("/api/system/backup");
      toast.dismiss();
      toast.success("Backup complete");
    } catch {
      toast.dismiss();
      toast.error("Backup failed");
    }
  };

  const renewCert = async () => {
    toast.loading("Renewing certificate...");
    try {
      const { data } = await api.post("/api/system/cert/renew");
      toast.dismiss();
      toast.success(data.code === 0 ? "Certificate renewed" : `Code ${data.code}`);
    } catch {
      toast.dismiss();
      toast.error("Renewal failed");
    }
  };

  return (
    <div className="p-6 max-w-5xl mx-auto">
      <h1 className="text-xl font-bold mono mb-6" style={{ color: "var(--cyan)" }}>Settings</h1>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Versions */}
        <Card title="Software Versions">
          <KV label="UniProxy"  value={versions?.uniproxy}  accent="var(--cyan)"    />
          <KV label="Xray-core" value={versions?.xray}      accent="var(--success)" />
          <KV label="Sing-box"  value={versions?.sing_box}  accent="var(--success)" />
        </Card>

        {/* System Resources */}
        <Card title="System Resources">
          {sysInfo ? (
            <>
              <KV label="CPU Cores"   value={sysInfo.cpu_cores} />
              <KV label="RAM Total"   value={`${sysInfo.ram.total_gb} GB`} />
              <KV label="RAM Used"    value={`${sysInfo.ram.used_gb} GB (${sysInfo.ram.pct}%)`}
                  accent={sysInfo.ram.pct > 85 ? "var(--danger)" : "var(--success)"} />
              <KV label="Disk Total"  value={`${sysInfo.disk.total_gb} GB`} />
              <KV label="Disk Used"   value={`${sysInfo.disk.used_gb} GB (${sysInfo.disk.pct}%)`}
                  accent={sysInfo.disk.pct > 85 ? "var(--danger)" : "var(--warn)"} />
              <KV label="Uptime"      value={`${sysInfo.uptime_hours}h`} accent="var(--cyan)" />
              <KV label="Net Sent"    value={`${sysInfo.network.sent_gb} GB`} />
              <KV label="Net Recv"    value={`${sysInfo.network.recv_gb} GB`} />
            </>
          ) : (
            <div className="text-center py-4 text-xs" style={{ color: "var(--text-muted)" }}>
              Loading system info…
            </div>
          )}
        </Card>

        {/* Service Control */}
        <Card title="Service Control">
          <ServiceBtn
            label="xray"
            onRestart={() => api.post("/api/system/xray/restart")}
            onStatus={()   => api.get("/api/system/xray/status")}
          />
          <ServiceBtn
            label="sing-box"
            onRestart={() => api.post("/api/system/singbox/restart")}
            onStatus={()   => api.get("/api/system/singbox/status")}
          />
          <div className="mt-3 flex flex-col gap-2">
            <button onClick={viewLogs}
              className="flex items-center gap-2 px-3 py-1.5 rounded text-xs w-full justify-center hover:bg-white/10 transition-colors"
              style={{ border: "1px solid var(--border)", color: "var(--text-muted)" }}>
              <Terminal size={12} /> View Logs
            </button>
          </div>
        </Card>

        {/* TLS Certificate */}
        <Card title="TLS Certificate">
          {certInfo ? (
            <>
              <KV label="Domain"     value={certInfo.domain} />
              <KV label="Valid"      value={certInfo.valid ? "Yes" : "No"}
                  accent={certInfo.valid ? "var(--success)" : "var(--danger)"} />
              {certInfo.not_before && <KV label="Not Before" value={certInfo.not_before} />}
              {certInfo.not_after  && <KV label="Not After"  value={certInfo.not_after}  />}
              <button onClick={renewCert}
                className="w-full mt-4 py-2 rounded text-xs font-semibold hover:opacity-90 transition-all"
                style={{ border: "1px solid var(--cyan)", color: "var(--cyan)", background: "transparent" }}>
                <Shield size={12} className="inline mr-1.5" />
                Renew Certificate
              </button>
            </>
          ) : (
            <div className="text-center py-4 text-xs" style={{ color: "var(--text-muted)" }}>
              Loading cert info…
            </div>
          )}
        </Card>

        {/* Backup */}
        <Card title="Backup & Restore">
          <p className="text-xs mb-4" style={{ color: "var(--text-muted)" }}>
            Backups include database, protocol configs, and subscription tokens.
            Auto-backup runs every 6 hours via cron.
          </p>
          <div className="flex gap-2">
            <button onClick={triggerBackup}
              className="flex-1 flex items-center justify-center gap-2 py-2 rounded text-xs font-semibold hover:opacity-90"
              style={{ background: "var(--success)", color: "#fff" }}>
              <Download size={12} /> Backup Now
            </button>
          </div>
        </Card>

        {/* About */}
        <Card title="About UniProxy">
          <div className="space-y-2 text-xs" style={{ color: "var(--text-muted)" }}>
            <p>Open-source unified proxy management panel.</p>
            <p>Supports 8+ protocols: Hysteria2, VLESS-Reality, ShadowTLS, Shadowsocks 2022, Trojan, TUIC, WireGuard, SSH.</p>
            <p>Config generation for: Sing-box, Clash, Hiddify, Shadowrocket, v2rayNG.</p>
            <div className="mt-3 pt-3" style={{ borderTop: "1px solid var(--border)" }}>
              <a href="https://github.com/franklin-lol/FVpn" target="_blank" rel="noopener"
                 className="hover:underline" style={{ color: "var(--cyan)" }}>
                GitHub Repository →
              </a>
            </div>
          </div>
        </Card>
      </div>

      {/* Log viewer */}
      {showLog && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4"
             style={{ background: "rgba(0,0,0,0.85)" }}>
          <div className="w-full max-w-3xl rounded-xl overflow-hidden box-glow"
               style={{ background: "var(--card)" }}>
            <div className="flex items-center justify-between px-5 py-3"
                 style={{ borderBottom: "1px solid var(--border)" }}>
              <span className="mono text-sm" style={{ color: "var(--cyan)" }}>
                /var/log/uniproxy.log
              </span>
              <button onClick={() => setShowLog(false)}
                      className="text-slate-500 hover:text-slate-300 text-xl">×</button>
            </div>
            <pre className="p-5 text-xs overflow-auto max-h-96 mono"
                 style={{ color: "#a8b4c8", background: "#060a14" }}>
              {logLines || "No log output"}
            </pre>
          </div>
        </div>
      )}
    </div>
  );
}
