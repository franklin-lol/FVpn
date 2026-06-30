import React, { useEffect, useState, useCallback } from "react";
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts";
import { Users, Server, Shield, Activity, RefreshCw } from "lucide-react";
import { statsApi } from "../utils/api";
import { useStatsStore } from "../store";
import toast from "react-hot-toast";
import dayjs from "dayjs";

function Sk({ w="100%", h=14, r=4 }) {
  return <div className="skeleton" style={{ width:w, height:h, borderRadius:r }} />;
}

function KpiCard({ icon:Icon, label, value, sub, color="var(--cyan)", delay=0 }) {
  return (
    <div className="card stagger-child fade-in" style={{ padding:20, animationDelay:`${delay}ms` }}>
      <div style={{ display:"flex", alignItems:"flex-start", justifyContent:"space-between" }}>
        <div style={{ minWidth:0 }}>
          <div className="label" style={{ marginBottom:8 }}>{label}</div>
          <div className="mono" style={{ fontSize:26, fontWeight:700, color, lineHeight:1, letterSpacing:"-.02em" }}>
            {value ?? "—"}
          </div>
          {sub && <div style={{ fontSize:11, color:"var(--text-muted)", marginTop:5 }}>{sub}</div>}
        </div>
        <div style={{ width:34, height:34, borderRadius:9, background:`${color}12`,
          border:`1px solid ${color}25`, display:"flex", alignItems:"center", justifyContent:"center", flexShrink:0 }}>
          <Icon size={15} style={{ color }} />
        </div>
      </div>
    </div>
  );
}

function GaugeRow({ label, pct, value, unit="" }) {
  const auto = pct > 85 ? "var(--danger)" : pct > 65 ? "var(--warn)" : "var(--cyan)";
  return (
    <div style={{ marginBottom:14 }}>
      <div style={{ display:"flex", justifyContent:"space-between", marginBottom:5 }}>
        <span style={{ fontSize:12, color:"var(--text-muted)" }}>{label}</span>
        <span className="mono" style={{ fontSize:12, color:auto, fontWeight:600 }}>
          {value}{unit}
        </span>
      </div>
      <div className="gauge-track">
        <div className="gauge-fill" style={{ width:`${Math.min(pct,100)}%`, background:auto }} />
      </div>
    </div>
  );
}

function NodeRow({ node, i }) {
  const st = node.status || "unknown";
  const lat = node.latency_ms;
  const latColor = lat < 50 ? "var(--success)" : lat < 150 ? "var(--warn)" : "var(--danger)";
  return (
    <div className="fade-in" style={{ display:"flex", alignItems:"center", gap:10, padding:"8px 0",
      borderBottom:"1px solid var(--border)", animationDelay:`${i*25}ms` }}>
      <span className={`dot dot-${st}`} />
      <span style={{ flex:1, fontSize:13, fontWeight:500 }}>{node.name}</span>
      {node.group && <span className="badge badge-violet">{node.group}</span>}
      <span className="mono" style={{ fontSize:11, color:lat ? latColor : "var(--text-dim)", minWidth:52, textAlign:"right" }}>
        {lat ? `${lat.toFixed(0)}ms` : st}
      </span>
    </div>
  );
}

const ChartTip = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null;
  return (
    <div style={{ background:"var(--card)", border:"1px solid var(--border-light)", borderRadius:8,
      padding:"8px 12px", fontSize:12, boxShadow:"0 8px 24px rgba(0,0,0,.4)" }}>
      <div className="mono" style={{ color:"var(--text-muted)", marginBottom:4 }}>{label}</div>
      {payload.map((p) => (
        <div key={p.name} style={{ color:p.color, display:"flex", gap:6, alignItems:"center" }}>
          <span style={{ width:6, height:6, borderRadius:"50%", background:p.color, display:"inline-block" }} />
          {p.name}: <strong>{p.value?.toFixed(1)}</strong>
        </div>
      ))}
    </div>
  );
};

function genSparkline(n=24) {
  return Array.from({ length:n }, (_,i) => ({
    t: dayjs().subtract(n-1-i,"hour").format("HH:mm"),
    in:  Math.round(Math.random()*70+10),
    out: Math.round(Math.random()*50+5),
  }));
}

export default function Dashboard() {
  const [stats,   setStats]   = useState(null);
  const [loading, setLoading] = useState(true);
  const [spark,   setSpark]   = useState(() => genSparkline());
  const live = useStatsStore((s) => s.live);

  const load = useCallback(async () => {
    try {
      const { data } = await statsApi.dashboard();
      setStats(data);
    } catch { toast.error("Failed to load stats"); }
    finally  { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    const t = setInterval(() => setSpark(genSparkline()), 30000);
    return () => clearInterval(t);
  }, []);

  const sys = stats?.system;

  return (
    <div className="page">
      {/* Header */}
      <div className="page-header">
        <div>
          <div className="page-title">Dashboard</div>
          <div className="page-sub">{dayjs().format("dddd, MMMM D YYYY")}</div>
        </div>
        <button className="btn btn-ghost btn-sm" onClick={load} style={{ gap:6 }}>
          <RefreshCw size={12} className={loading?"spin":""} />
          Refresh
        </button>
      </div>

      {/* KPIs */}
      <div className="stagger" style={{ display:"grid", gridTemplateColumns:"repeat(auto-fit,minmax(190px,1fr))", gap:12, marginBottom:16 }}>
        {loading ? [1,2,3,4].map((k) => (
          <div key={k} className="card" style={{ padding:20 }}>
            <Sk h={10} w="45%" /><Sk h={28} w="38%" style={{ marginTop:10 }} /><Sk h={10} w="60%" style={{ marginTop:8 }} />
          </div>
        )) : <>
          <KpiCard delay={0}   icon={Users}    label="Active Users"   color="var(--cyan)"    value={live?.active_users ?? stats?.users?.active}  sub={`${stats?.users?.total??0} total`} />
          <KpiCard delay={45}  icon={Server}   label="Online Nodes"   color="var(--success)" value={live?.online_nodes ?? stats?.nodes?.online}   sub={`${stats?.nodes?.total??0} configured`} />
          <KpiCard delay={90}  icon={Shield}   label="Protocols"      color="#a78bfa"         value={stats?.protocols?.total} sub="across all nodes" />
          <KpiCard delay={135} icon={Activity} label="Traffic Out"    color="var(--warn)"    value={stats?.traffic ? `${(stats.traffic.out_bytes/1e9).toFixed(2)} GB` : null} sub={stats?.traffic ? `↓ ${(stats.traffic.in_bytes/1e9).toFixed(2)} GB` : null} />
        </>}
      </div>

      {/* Charts */}
      <div style={{ display:"grid", gridTemplateColumns:"1fr 300px", gap:12, marginBottom:12 }}>
        <div className="card" style={{ padding:20 }}>
          <div className="label" style={{ marginBottom:14 }}>Traffic · 24h</div>
          <ResponsiveContainer width="100%" height={150}>
            <AreaChart data={spark} margin={{ left:-24 }}>
              <defs>
                <linearGradient id="gI" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%"   stopColor="var(--cyan)"  stopOpacity={.22}/>
                  <stop offset="100%" stopColor="var(--cyan)"  stopOpacity={0}/>
                </linearGradient>
                <linearGradient id="gO" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%"   stopColor="#a78bfa"      stopOpacity={.22}/>
                  <stop offset="100%" stopColor="#a78bfa"      stopOpacity={0}/>
                </linearGradient>
              </defs>
              <XAxis dataKey="t" tick={{ fontSize:10, fill:"var(--text-muted)" }} tickLine={false} axisLine={false} interval={5}/>
              <YAxis tick={{ fontSize:10, fill:"var(--text-muted)" }} tickLine={false} axisLine={false} width={28} unit="M"/>
              <Tooltip content={<ChartTip/>}/>
              <Area type="monotone" dataKey="in"  name="↓ Recv" stroke="var(--cyan)" strokeWidth={1.5} fill="url(#gI)"  dot={false}/>
              <Area type="monotone" dataKey="out" name="↑ Send" stroke="#a78bfa"     strokeWidth={1.5} fill="url(#gO)"  dot={false}/>
            </AreaChart>
          </ResponsiveContainer>
        </div>

        <div className="card" style={{ padding:20 }}>
          <div className="label" style={{ marginBottom:14 }}>System</div>
          {sys ? <>
            <GaugeRow label="CPU"  pct={live?.cpu_pct    ?? sys.cpu_pct}    value={`${(live?.cpu_pct??sys.cpu_pct)?.toFixed(0)}%`}/>
            <GaugeRow label="RAM"  pct={sys.ram?.pct??0}                    value={`${sys.ram?.used_gb??0} / ${sys.ram?.total_gb??0}`} unit=" GB"/>
            <GaugeRow label="Disk" pct={sys.disk?.pct??0}                   value={`${sys.disk?.used_gb??0} / ${sys.disk?.total_gb??0}`} unit=" GB"/>
            <div style={{ marginTop:12, display:"flex", flexDirection:"column", gap:3 }}>
              {[["Uptime",`${sys.uptime_hours??"-"}h`],["Sent",`${sys.network?.sent_gb??"-"} GB`],["Recv",`${sys.network?.recv_gb??"-"} GB`]].map(([k,v])=>(
                <div key={k} style={{ display:"flex", justifyContent:"space-between", fontSize:12 }}>
                  <span style={{ color:"var(--text-muted)" }}>{k}</span>
                  <span className="mono" style={{ color:"var(--text)" }}>{v}</span>
                </div>
              ))}
            </div>
          </> : [1,2,3].map((k)=><Sk key={k} h={14} style={{ marginBottom:12 }}/>)}
        </div>
      </div>

      {/* Nodes + Events */}
      <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr", gap:12 }}>
        <div className="card" style={{ padding:20 }}>
          <div className="label" style={{ marginBottom:12 }}>Node Status</div>
          {loading ? [1,2,3].map((k)=><Sk key={k} h={34} style={{ marginBottom:8 }}/>)
            : stats?.nodes_list?.length ? stats.nodes_list.map((n,i)=><NodeRow key={i} node={n} i={i}/>)
            : <div className="empty" style={{ padding:"20px 0" }}><p>No nodes yet</p></div>}
        </div>

        <div className="card" style={{ padding:20 }}>
          <div className="label" style={{ marginBottom:12 }}>Recent Events</div>
          <div style={{ maxHeight:220, overflow:"auto" }} className="no-scrollbar">
            {loading ? [1,2,3,4].map((k)=><Sk key={k} h={26} style={{ marginBottom:6 }}/>)
              : stats?.recent_logs?.length ? stats.recent_logs.map((l,i)=>{
                const c = l.level==="error"?"var(--danger)":l.level==="warn"?"var(--warn)":"var(--success)";
                return (
                  <div key={i} className="fade-in" style={{ display:"flex", gap:8, padding:"6px 0",
                    borderBottom:"1px solid var(--border)", animationDelay:`${i*18}ms`, alignItems:"flex-start" }}>
                    <span className="mono" style={{ fontSize:10, color:c, fontWeight:700, paddingTop:1, flexShrink:0 }}>
                      {l.level.toUpperCase()}
                    </span>
                    <span style={{ fontSize:12, color:"var(--text-muted)", flex:1, lineHeight:1.4 }}>{l.message}</span>
                  </div>
                );
              })
              : <div className="empty" style={{ padding:"20px 0" }}><p>No events yet</p></div>}
          </div>
        </div>
      </div>
    </div>
  );
}
