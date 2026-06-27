import React, { useEffect } from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { Toaster } from "react-hot-toast";
import { useAuthStore, useStatsStore } from "./store";

import Login     from "./pages/Login";
import Dashboard from "./pages/Dashboard";
import Nodes     from "./pages/Nodes";
import Users     from "./pages/Users";
import Protocols from "./pages/Protocols";
import Settings  from "./pages/Settings";
import Layout    from "./components/Layout";

function PrivateRoute({ children }) {
  const token = useAuthStore((s) => s.token);
  return token ? children : <Navigate to="/login" replace />;
}

function WSFeed() {
  const token   = useAuthStore((s) => s.token);
  const setLive = useStatsStore((s) => s.setLive);

  useEffect(() => {
    if (!token) return;
    const proto = window.location.protocol === "https:" ? "wss" : "ws";
    const ws = new WebSocket(`${proto}://${window.location.host}/ws/stats?token=${token}`);
    ws.onmessage = (e) => {
      try { setLive(JSON.parse(e.data)); } catch {}
    };
    ws.onerror = () => {};
    const ping = setInterval(() => ws.readyState === 1 && ws.send("ping"), 15000);
    return () => { clearInterval(ping); ws.close(); };
  }, [token, setLive]);

  return null;
}

export default function App() {
  const hydrate = useAuthStore((s) => s.hydrate);
  useEffect(() => { hydrate(); }, []);

  return (
    <BrowserRouter>
      <WSFeed />
      <Toaster
        position="top-right"
        toastOptions={{
          style: { background: "#1a2340", color: "#e2e8f0", border: "1px solid #243050" },
          success: { iconTheme: { primary: "#10b981", secondary: "#0a0e1a" } },
          error:   { iconTheme: { primary: "#ef4444", secondary: "#0a0e1a" } },
        }}
      />
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/" element={<PrivateRoute><Layout /></PrivateRoute>}>
          <Route index element={<Navigate to="/dashboard" replace />} />
          <Route path="dashboard" element={<Dashboard />} />
          <Route path="nodes"     element={<Nodes />} />
          <Route path="users"     element={<Users />} />
          <Route path="protocols" element={<Protocols />} />
          <Route path="settings"  element={<Settings />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
