import React, { useState } from "react";
import { Outlet, NavLink, useNavigate } from "react-router-dom";
import {
  LayoutDashboard, Server, Users, Shield,
  Settings, LogOut, Terminal, ChevronLeft, ChevronRight,
  Wifi, Activity
} from "lucide-react";
import { useAuthStore, useStatsStore } from "../store";
import clsx from "clsx";

const NAV = [
  { to: "/dashboard", icon: LayoutDashboard, label: "Dashboard" },
  { to: "/nodes",     icon: Server,          label: "Nodes"     },
  { to: "/users",     icon: Users,           label: "Users"     },
  { to: "/protocols", icon: Shield,          label: "Protocols" },
  { to: "/settings",  icon: Settings,        label: "Settings"  },
];

function LiveBadge() {
  const live = useStatsStore((s) => s.live);
  if (!live) return null;
  return (
    <div className="flex items-center gap-2 text-xs mono px-3 py-1 rounded" style={{background:"#0f1629",color:"#00d4ff"}}>
      <span className="dot-online pulse" />
      <span>{live.online_nodes ?? "--"} nodes</span>
      <span style={{color:"#64748b"}}>|</span>
      <span>CPU {live.cpu_pct ?? "--"}%</span>
    </div>
  );
}

export default function Layout() {
  const [collapsed, setCollapsed] = useState(false);
  const logout   = useAuthStore((s) => s.logout);
  const username = useAuthStore((s) => s.user);
  const navigate = useNavigate();

  const handleLogout = () => { logout(); navigate("/login"); };

  return (
    <div className="scanlines flex h-full" style={{minHeight:"100vh"}}>
      {/* ── SIDEBAR ── */}
      <aside
        className="flex flex-col flex-shrink-0 transition-all duration-200"
        style={{
          width: collapsed ? 56 : 220,
          background: "var(--surface)",
          borderRight: "1px solid var(--border)",
        }}
      >
        {/* Logo */}
        <div className="flex items-center gap-3 px-4 py-5" style={{borderBottom:"1px solid var(--border)"}}>
          <div className="flex-shrink-0 w-7 h-7 rounded flex items-center justify-center"
               style={{background:"linear-gradient(135deg,#00d4ff,#7c3aed)"}}>
            <Shield size={14} color="#fff" />
          </div>
          {!collapsed && (
            <span className="font-bold text-sm tracking-widest mono" style={{color:"var(--cyan)"}}>
              UNIPROXY
            </span>
          )}
        </div>

        {/* Nav */}
        <nav className="flex-1 py-4 flex flex-col gap-1 px-2">
          {NAV.map(({ to, icon: Icon, label }) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) =>
                clsx(
                  "flex items-center gap-3 px-2 py-2 rounded transition-all duration-150 text-sm font-medium",
                  isActive
                    ? "bg-cyan-950/50 text-cyan-400 box-glow-cyan"
                    : "text-slate-400 hover:text-slate-200 hover:bg-white/5"
                )
              }
              style={({ isActive }) => ({
                color: isActive ? "var(--cyan)" : undefined,
                borderLeft: isActive ? "2px solid var(--cyan)" : "2px solid transparent",
                paddingLeft: isActive ? 6 : 8,
              })}
              title={collapsed ? label : undefined}
            >
              <Icon size={16} className="flex-shrink-0" />
              {!collapsed && <span>{label}</span>}
            </NavLink>
          ))}
        </nav>

        {/* Live stats mini */}
        {!collapsed && (
          <div className="px-3 pb-2">
            <LiveBadge />
          </div>
        )}

        {/* Footer */}
        <div className="px-2 py-3 flex flex-col gap-2" style={{borderTop:"1px solid var(--border)"}}>
          {!collapsed && (
            <div className="px-2 py-1 text-xs mono" style={{color:"var(--text-muted)"}}>
              {username}
            </div>
          )}
          <button
            onClick={handleLogout}
            className="flex items-center gap-3 px-2 py-2 rounded text-sm text-slate-400 hover:text-red-400 hover:bg-white/5 transition-colors"
            title="Logout"
          >
            <LogOut size={16} className="flex-shrink-0" />
            {!collapsed && <span>Logout</span>}
          </button>
          <button
            onClick={() => setCollapsed(!collapsed)}
            className="flex items-center gap-3 px-2 py-2 rounded text-sm text-slate-500 hover:text-slate-300 hover:bg-white/5 transition-colors"
          >
            {collapsed ? <ChevronRight size={16} /> : <><ChevronLeft size={16}/><span className="text-xs">Collapse</span></>}
          </button>
        </div>
      </aside>

      {/* ── MAIN ── */}
      <main className="flex-1 overflow-auto fade-in" style={{background:"var(--bg)"}}>
        <Outlet />
      </main>
    </div>
  );
}
