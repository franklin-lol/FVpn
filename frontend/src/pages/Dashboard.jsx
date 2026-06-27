import React, { useEffect, useState, useCallback } from "react";
import {
  AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer,
  BarChart, Bar, Cell
} from "recharts";
import { Server, Users, Shield, Activity, Cpu, HardDrive, Wifi, RefreshCw } from "lucide-react";
import { statsApi } from "../utils/api";
import { useStatsStore } from "../store";
import toast from "react-hot-toast";
import dayjs from "dayjs";

function StatCard({ icon: Icon, label, value, sub, color = "var(--cyan)", accent }) {
  return (
    <div className="rounded-lg p-4 box-glow fade-in flex items-start gap-4"
         style={{ background: "var(--card)" }}>
      <div className="p-2 rounded-lg flex-shrink-0"
           style={{ background: `${color}18`, border: `1px solid ${color}40` }}>
        <Icon size={18} style={{ color }} />
      </div>
      <div>
        <div className="text-xs uppercase tracking-widest mb-1" style={{ color: "var(--text-muted)" }}>
          {label}
        </div>
        <div className="text-2xl font-bold mono" style={{ color }}>
          {value ?? "—"}
        </div>
        {sub && <div className="text-xs mt-0.5" style={{ color: "var(--text-muted)" }}>{sub}</div>}
      </div>
    </div>
  );
}

function GaugeBar({ label, pct, color }) {
  return (
    <div className="mb-3">
      <div className="flex justify-between text-xs mb-1" style={{ color: "var(--text-muted)" }}>
        <span>{label}</span>
        <span className="mono" style={{ color }}>{pct?.toFixed(1)}%</span>
      </div>
      <div className="h-1.5 rounded-full" style={{ background: "var(--border)" }}>
        <div className="h-full rounded-full transition-all duration-700"
             style={{ width: `${Math.min(pct || 0, 100)}%`, background: color }} />
      </div>
    </div>
  );
}

function NodeRow({ node }) {
  const statusColor = node.status === "online" ? "var(--success)" : node.status === "offline" ? "var(--danger)" : "var(--text-muted)";
  return (
    <div className="flex items-center gap-3 px-3 py-2 rounded hover:bg-white/5 transition-colors">
      <span className={`dot-${node.status}`} />
      <span className="flex-1 text-sm">{node.name}</span>
      {node.group && (
        <span className="text-xs px-2 py-0.5 rounded" style={{ background: "var(--border)", color: "var(--text-muted)" }}>
          {node.group}
        </span>
      )}
      <span className="text-xs mono" style={{ color: statusColor }}>
        {node.latency_ms ? `${node.latency_ms.toFixed(0)}ms` : node.status}
      </span>
    </div>
  );
}

// Mock sparkline data generator (replace with real time-series from backend)
function genSparkline(n = 24) {
  return Array.from({ length: n }, (_, i) => ({
    t: dayjs().subtract(n - 1 - i, "hour").format("HH:mm"),
    in: Math.random() * 80 + 5,
    out: Math.random() * 60 + 3,
  }));
}

export default function Dashboard() {
  const [stats,    setStats]    = useState(null);
  const [loading,  setLoading]  = useState(true);
  const [sparkline, setSparkline] = useState(genSparkline());
  const live = useStatsStore((s) => s.live);

  const fetch = useCallback(async () => {
    try {
      const { data } = await statsApi.dashboard();
      setStats(data);
    } catch {
      toast.error("Failed to load stats");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetch(); }, [fetch]);

  // Refresh sparkline every 30s
  useEffect(() => {
    const t = setInterval(() => setSparkline(genSparkline()), 30000);
    return () => clearInterval(t);
  }, []);

  const sys = stats?.system;

  return (
    <div className="p-6 max-w-7xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-bold mono" style={{ color: "var(--cyan)" }}>
            Dashboard
          </h1>
          <p className="text-xs mt-1" style={{ color: "var(--text-muted)" }}>
            {dayjs().format("dddd, MMMM D YYYY · HH:mm")}
          </p>
        </div>
        <button
          onClick={fetch}
          className="flex items-center gap-2 px-3 py-1.5 rounded text-sm transition-colors hover:bg-white/10"
          style={{ border: "1px solid var(--border)", color: "var(--text-muted)" }}
        >
          <RefreshCw size={13} className={loading ? "animate-spin" : ""} />
          Refresh
        </button>
      </div>

      {/* KPI row */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        <StatCard
          icon={Users}  label="Active Users"
          value={live?.active_users ?? stats?.users?.active}
          sub={`of ${stats?.users?.total ?? 0} total`}
          color="var(--cyan)"
        />
        <StatCard
          icon={Server} label="Online Nodes"
          value={live?.online_nodes ?? stats?.nodes?.online}
          sub={`of ${stats?.nodes?.total ?? 0} total`}
          color="var(--success)"
        />
        <StatCard
          icon={Shield} label="Protocols"
          value={stats?.protocols?.total}
          color="var(--violet)"
        />
        <StatCard
          icon={Activity} label="Traffic (↑)"
          value={stats?.traffic ? `${(stats.traffic.out_bytes / 1e9).toFixed(2)} GB` : null}
          sub={`↓ ${stats?.traffic ? (stats.traffic.in_bytes / 1e9).toFixed(2) : "—"} GB recv`}
          color="var(--warn)"
        />
      </div>

      {/* Charts row */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 mb-6">
        {/* Traffic sparkline */}
        <div className="lg:col-span-2 rounded-lg p-4 box-glow" style={{ background: "var(--card)" }}>
          <div className="text-xs uppercase tracking-widest mb-4" style={{ color: "var(--text-muted)" }}>
            Traffic (24h)
          </div>
          <ResponsiveContainer width="100%" height={180}>
            <AreaChart data={sparkline}>
              <defs>
                <linearGradient id="gin"  x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%"   stopColor="#00d4ff" stopOpacity={0.3} />
                  <stop offset="100%" stopColor="#00d4ff" stopOpacity={0}   />
                </linearGradient>
                <linearGradient id="gout" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%"   stopColor="#7c3aed" stopOpacity={0.3} />
                  <stop offset="100%" stopColor="#7c3aed" stopOpacity={0}   />
                </linearGradient>
              </defs>
              <XAxis dataKey="t" tick={{ fontSize: 10, fill: "#64748b" }} tickLine={false} axisLine={false} interval={5} />
              <YAxis tick={{ fontSize: 10, fill: "#64748b" }} tickLine={false} axisLine={false} width={35} unit=" M" />
              <Tooltip
                contentStyle={{ background: "#0f1629", border: "1px solid #243050", borderRadius: 6, fontSize: 11 }}
                labelStyle={{ color: "#64748b" }}
              />
              <Area type="monotone" dataKey="in"  stroke="#00d4ff" strokeWidth={1.5} fill="url(#gin)"  name="↓ Recv" />
              <Area type="monotone" dataKey="out" stroke="#7c3aed" strokeWidth={1.5} fill="url(#gout)" name="↑ Send" />
            </AreaChart>
          </ResponsiveContainer>
        </div>

        {/* System resources */}
        <div className="rounded-lg p-4 box-glow" style={{ background: "var(--card)" }}>
          <div className="text-xs uppercase tracking-widest mb-4" style={{ color: "var(--text-muted)" }}>
            System Resources
          </div>
          <GaugeBar label="CPU"  pct={live?.cpu_pct  ?? sys?.cpu_pct}  color="var(--cyan)"   />
          <GaugeBar label="RAM"  pct={live?.ram_pct  ?? sys?.ram_pct}  color="var(--violet)" />
          <GaugeBar label="Disk" pct={sys?.disk_pct}                   color="var(--warn)"   />
          <div className="mt-4 space-y-1 text-xs mono" style={{ color: "var(--text-muted)" }}>
            <div>RAM: {live?.ram_used_gb ?? sys?.ram_used_gb ?? "—"} / {sys?.ram_total_gb ?? "—"} GB</div>
            <div>Disk: {sys?.disk_used_gb ?? "—"} / {sys?.disk_total_gb ?? "—"} GB</div>
            <div>Uptime: {sys?.uptime_hours ?? "—"}h</div>
          </div>
        </div>
      </div>

      {/* Nodes + Logs */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Node list */}
        <div className="rounded-lg p-4 box-glow" style={{ background: "var(--card)" }}>
          <div className="text-xs uppercase tracking-widest mb-3" style={{ color: "var(--text-muted)" }}>
            Nodes Status
          </div>
          {stats?.nodes_list?.length
            ? stats.nodes_list.map((n, i) => <NodeRow key={i} node={n} />)
            : <div className="text-sm text-center py-6" style={{ color: "var(--text-muted)" }}>No nodes configured</div>
          }
        </div>

        {/* Recent logs */}
        <div className="rounded-lg p-4 box-glow" style={{ background: "var(--card)" }}>
          <div className="text-xs uppercase tracking-widest mb-3" style={{ color: "var(--text-muted)" }}>
            Recent Events
          </div>
          <div className="space-y-2 max-h-64 overflow-y-auto">
            {stats?.recent_logs?.length
              ? stats.recent_logs.map((l, i) => (
                  <div key={i} className="flex items-start gap-2 text-xs">
                    <span className="mono flex-shrink-0" style={{
                      color: l.level === "error" ? "var(--danger)" : l.level === "warn" ? "var(--warn)" : "var(--success)"
                    }}>
                      [{l.level.toUpperCase()}]
                    </span>
                    <span style={{ color: "var(--text-muted)" }}>{l.source}</span>
                    <span className="flex-1">{l.message}</span>
                  </div>
                ))
              : <div className="text-sm text-center py-6" style={{ color: "var(--text-muted)" }}>No events</div>
            }
          </div>
        </div>
      </div>
    </div>
  );
}
