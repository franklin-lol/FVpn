import React, { useEffect } from "react";
import { BrowserRouter, Routes, Route, Navigate, useLocation } from "react-router-dom";
import { Toaster } from "react-hot-toast";
import { useAuthStore, useI18n, usePreferences } from "./store";
import useRemote from "./utils/useRemote";
import api from "./utils/api";
import { Button, Card, ErrorState, Loading } from "./components/ui";
import Login from "./pages/Login";
import Dashboard from "./pages/Dashboard";
import Nodes from "./pages/Nodes";
import Users from "./pages/Users";
import Protocols from "./pages/Protocols";
import Settings from "./pages/Settings";
import Setup from "./pages/Setup";
import Connect from "./pages/Connect";
import Layout from "./components/Layout";

function Theme() {
  const { theme, language } = usePreferences();
  useEffect(() => {
    const query = window.matchMedia("(prefers-color-scheme: dark)");
    const apply = () => { document.documentElement.dataset.theme = theme === "system" ? (query.matches ? "dark" : "light") : theme; };
    apply(); query.addEventListener("change", apply);
    return () => query.removeEventListener("change", apply);
  }, [theme]);
  useEffect(() => { document.documentElement.lang = language; }, [language]);
  return null;
}
function AdminBoundary({ children }) {
  const { token, isAdmin, logout } = useAuthStore();
  const { t } = useI18n();
  if (!token) return <Navigate to="/login" replace />;
  if (!isAdmin) return <div className="page"><Card className="space-y-4"><h1>{t("Эта панель для администратора", "Administrator access required")}</h1><p className="muted">{t("Для подключения устройства откройте личную ссылку от администратора.", "To connect a device, open the private link provided by your administrator.")}</p><Button onClick={logout}>{t("Выйти", "Sign out")}</Button></Card></div>;
  return children;
}
function SetupBoundary({ children }) {
  const location = useLocation();
  const { data, loading, error, reload } = useRemote(async () => (await api.get("/api/setup")).data);
  if (loading) return <div className="page"><Loading /></div>;
  if (error) return <div className="page"><ErrorState message={error} onRetry={reload} /></div>;
  // Advanced pages remain accessible when recovering an incomplete install.
  if (data.required && !["/nodes", "/protocols", "/settings"].includes(location.pathname)) return <Navigate to="/setup" replace />;
  return children;
}
export default function App() {
  const hydrate = useAuthStore((s) => s.hydrate);
  useEffect(() => { hydrate(); }, [hydrate]);
  return <BrowserRouter><Theme /><Toaster position="top-right" toastOptions={{ style: { background: "var(--surface)", color: "var(--text)", border: "1px solid var(--border)" } }} /><Routes>
    <Route path="/login" element={<Login />} />
    <Route path="/s/:token" element={<Connect />} />
    <Route path="/setup" element={<AdminBoundary><Setup /></AdminBoundary>} />
    <Route path="/" element={<AdminBoundary><SetupBoundary><Layout /></SetupBoundary></AdminBoundary>}>
      <Route index element={<Navigate to="/dashboard" replace />} />
      <Route path="dashboard" element={<Dashboard />} /><Route path="nodes" element={<Nodes />} /><Route path="users" element={<Users />} /><Route path="protocols" element={<Protocols />} /><Route path="settings" element={<Settings />} />
    </Route><Route path="*" element={<Navigate to="/" replace />} />
  </Routes></BrowserRouter>;
}
