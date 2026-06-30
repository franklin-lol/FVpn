import React, { useState } from "react";
import { Outlet, NavLink, useNavigate, useLocation } from "react-router-dom";
import { LayoutDashboard, Server, Users, Shield, Settings, LogOut, ChevronLeft, ChevronRight, Zap } from "lucide-react";
import { useAuthStore, useStatsStore } from "../store";

const NAV = [
  { to:"/dashboard", icon:LayoutDashboard, label:"Dashboard" },
  { to:"/nodes",     icon:Server,          label:"Nodes"     },
  { to:"/users",     icon:Users,           label:"Users"     },
  { to:"/protocols", icon:Shield,          label:"Protocols" },
  { to:"/settings",  icon:Settings,        label:"Settings"  },
];

const PAGE_TITLES = { "/dashboard":"Dashboard", "/nodes":"Nodes", "/users":"Users", "/protocols":"Protocols", "/settings":"Settings" };

function LivePill() {
  const live = useStatsStore((s) => s.live);
  if (!live) return null;
  const cpuBad = (live.cpu_pct || 0) > 80;
  return (
    <div style={{ display:"flex", alignItems:"center", gap:6, fontSize:11, fontFamily:"JetBrains Mono,monospace",
      padding:"3px 9px", borderRadius:99, background:"rgba(0,212,255,.06)", border:"1px solid rgba(0,212,255,.15)",
      color:"var(--text-muted)", whiteSpace:"nowrap" }}>
      <span className="dot dot-online" style={{ width:6, height:6 }} />
      <span style={{ color:"var(--cyan)", fontWeight:600 }}>{live.online_nodes ?? "—"}</span>
      <span style={{ color:"var(--text-dim)" }}>·</span>
      <span style={{ color: cpuBad ? "var(--warn)" : "var(--success)", fontWeight:600 }}>
        CPU {live.cpu_pct?.toFixed(0) ?? "—"}%
      </span>
    </div>
  );
}

export default function Layout() {
  const [collapsed, setCollapsed] = useState(false);
  const logout    = useAuthStore((s) => s.logout);
  const username  = useAuthStore((s) => s.user);
  const navigate  = useNavigate();
  const location  = useLocation();
  const pageTitle = PAGE_TITLES[location.pathname] || "FVpn";
  const initials  = (username || "A").slice(0, 2).toUpperCase();

  const W = collapsed ? 60 : 220;

  return (
    <div className="scanlines" style={{ display:"flex", minHeight:"100vh" }}>
      {/* ── Sidebar ── */}
      <aside style={{
        width: W, flexShrink:0,
        transition:"width .22s cubic-bezier(.4,0,.2,1)",
        background:"var(--surface)",
        borderRight:"1px solid var(--border)",
        display:"flex", flexDirection:"column",
        overflow:"hidden", position:"relative", zIndex:10,
      }}>
        {/* Logo */}
        <div style={{ height:56, display:"flex", alignItems:"center", gap:10, padding:"0 14px",
          borderBottom:"1px solid var(--border)", flexShrink:0 }}>
          <div style={{ width:28, height:28, borderRadius:8, flexShrink:0,
            background:"linear-gradient(135deg,rgba(0,212,255,.22),rgba(124,58,237,.22))",
            border:"1px solid rgba(0,212,255,.28)",
            display:"flex", alignItems:"center", justifyContent:"center",
            boxShadow:"0 0 14px rgba(0,212,255,.1)" }}>
            <Zap size={14} style={{ color:"var(--cyan)" }} />
          </div>
          <div style={{ overflow:"hidden", opacity:collapsed?0:1, transform:collapsed?"translateX(-6px)":"none",
            transition:"opacity .18s,transform .18s", pointerEvents:collapsed?"none":"auto", whiteSpace:"nowrap" }}>
            <div style={{ fontFamily:"JetBrains Mono,monospace", fontWeight:700, fontSize:15,
              color:"var(--cyan)", letterSpacing:".06em" }}>FVpn</div>
            <div style={{ fontSize:9, color:"var(--text-dim)", letterSpacing:".1em", marginTop:-1 }}>PROXY PANEL</div>
          </div>
        </div>

        {/* Nav */}
        <nav style={{ flex:1, padding:"10px 7px", display:"flex", flexDirection:"column", gap:2 }}>
          {NAV.map(({ to, icon:Icon, label }) => (
            <NavLink key={to} to={to} title={collapsed ? label : undefined}
              style={({ isActive }) => ({
                display:"flex", alignItems:"center", gap:9, padding:"8px 9px",
                borderRadius:8, fontSize:13, fontWeight:isActive?600:400,
                cursor:"pointer", textDecoration:"none",
                transition:"background .12s,color .12s,border-color .12s",
                color: isActive?"var(--cyan)":"var(--text-muted)",
                background: isActive?"rgba(0,212,255,.07)":"transparent",
                borderLeft:`2px solid ${isActive?"var(--cyan)":"transparent"}`,
                paddingLeft: isActive?7:9,
                overflow:"hidden", whiteSpace:"nowrap",
              })}>
              {({ isActive }) => (
                <>
                  <Icon size={15} style={{ flexShrink:0,
                    color:isActive?"var(--cyan)":undefined,
                    filter:isActive?"drop-shadow(0 0 5px rgba(0,212,255,.55))":"none",
                    transition:"filter .15s" }} />
                  <span style={{ opacity:collapsed?0:1, transform:collapsed?"translateX(-4px)":"none",
                    transition:"opacity .15s,transform .15s", pointerEvents:collapsed?"none":"auto" }}>
                    {label}
                  </span>
                </>
              )}
            </NavLink>
          ))}
        </nav>

        {/* Footer */}
        <div style={{ borderTop:"1px solid var(--border)", padding:"8px 7px", display:"flex",
          flexDirection:"column", gap:4, flexShrink:0 }}>
          {!collapsed && (
            <div style={{ padding:"0 2px 4px" }}><LivePill /></div>
          )}
          {/* User */}
          <div style={{ display:"flex", alignItems:"center", gap:8, padding:"5px 7px",
            borderRadius:8, overflow:"hidden" }}>
            <div style={{ width:26, height:26, borderRadius:7, flexShrink:0,
              background:"linear-gradient(135deg,var(--cyan),var(--violet))",
              display:"flex", alignItems:"center", justifyContent:"center",
              fontSize:10, fontWeight:700, color:"#fff", letterSpacing:".04em" }}>
              {initials}
            </div>
            <div style={{ overflow:"hidden", opacity:collapsed?0:1,
              transition:"opacity .15s", pointerEvents:collapsed?"none":"auto" }}>
              <div style={{ fontSize:12, fontWeight:600, color:"var(--text)", whiteSpace:"nowrap" }}>{username}</div>
              <div style={{ fontSize:10, color:"var(--text-muted)" }}>Admin</div>
            </div>
          </div>
          {/* Logout */}
          <button onClick={() => { logout(); navigate("/login"); }}
            style={{ display:"flex", alignItems:"center", gap:8, padding:"7px 8px", borderRadius:8,
              fontSize:13, color:"var(--text-muted)", background:"transparent", border:"none",
              cursor:"pointer", transition:"background .12s,color .12s", width:"100%",
              textAlign:"left", overflow:"hidden", whiteSpace:"nowrap" }}
            onMouseEnter={(e) => { e.currentTarget.style.background="rgba(239,68,68,.08)"; e.currentTarget.style.color="var(--danger)"; }}
            onMouseLeave={(e) => { e.currentTarget.style.background="transparent"; e.currentTarget.style.color="var(--text-muted)"; }}>
            <LogOut size={14} style={{ flexShrink:0 }} />
            <span style={{ opacity:collapsed?0:1, transition:"opacity .15s" }}>Sign out</span>
          </button>
          {/* Collapse */}
          <button onClick={() => setCollapsed(!collapsed)}
            style={{ display:"flex", alignItems:"center", justifyContent:collapsed?"center":"flex-start",
              gap:7, padding:"5px 8px", borderRadius:8, fontSize:12, color:"var(--text-dim)",
              background:"transparent", border:"none", cursor:"pointer",
              transition:"all .12s", width:"100%" }}
            onMouseEnter={(e) => { e.currentTarget.style.color="var(--text-muted)"; e.currentTarget.style.background="rgba(255,255,255,.03)"; }}
            onMouseLeave={(e) => { e.currentTarget.style.color="var(--text-dim)"; e.currentTarget.style.background="transparent"; }}>
            {collapsed ? <ChevronRight size={13} /> : <><ChevronLeft size={13} /><span>Collapse</span></>}
          </button>
        </div>
      </aside>

      {/* ── Main ── */}
      <div style={{ flex:1, display:"flex", flexDirection:"column", minWidth:0, overflow:"hidden" }}>
        {/* Topbar */}
        <header style={{ height:56, display:"flex", alignItems:"center", justifyContent:"space-between",
          padding:"0 24px", borderBottom:"1px solid var(--border)",
          background:"var(--surface)", flexShrink:0 }}>
          <div style={{ fontFamily:"JetBrains Mono,monospace", fontWeight:600, fontSize:14, color:"var(--text)" }}>
            {pageTitle}
          </div>
          <div style={{ display:"flex", alignItems:"center", gap:10 }}>
            <LivePill />
            <div style={{ fontSize:10, fontFamily:"JetBrains Mono,monospace", color:"var(--text-dim)",
              padding:"2px 8px", borderRadius:99, border:"1px solid var(--border)" }}>v1.0</div>
          </div>
        </header>
        {/* Content */}
        <main className="fade-in" style={{ flex:1, overflow:"auto", background:"var(--bg)" }}>
          <Outlet />
        </main>
      </div>
    </div>
  );
}
