import React, { useState } from "react";
import { Navigate } from "react-router-dom";
import { ArrowRight, Eye, EyeOff, ShieldCheck } from "lucide-react";
import { useAuthStore, useI18n } from "../store";
import { Button, Card, Field } from "../components/ui";
import { PreferencesControls } from "../components/Layout";

export default function Login() {
  const { t } = useI18n();
  const { token, login } = useAuthStore();
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("");
  const [show, setShow] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  if (token) return <Navigate to="/" replace />;
  const submit = async (event) => {
    event.preventDefault(); setBusy(true); setError("");
    try { await login(username, password); }
    catch (error) { setError(error.response?.status === 429 ? t("Слишком много попыток. Повторите через 15 минут.", "Too many attempts. Try again in 15 minutes.") : error.response?.status === 401 ? t("Проверьте имя и пароль и повторите.", "Check your username and password and try again.") : t("Сервер недоступен. Проверьте соединение и повторите.", "Server unavailable. Check your connection and try again.")); }
    finally { setBusy(false); }
  };
  return <div className="min-h-dvh"><header className="flex justify-end p-4 sm:p-6"><PreferencesControls /></header><main className="mx-auto grid max-w-5xl gap-10 px-4 pb-12 pt-8 sm:px-8 lg:grid-cols-2 lg:items-center lg:gap-20 lg:pt-20"><div className="space-y-6"><div className="icon-box !h-14 !w-14"><ShieldCheck size={30} /></div><span className="badge badge-accent">FVpn · {t("Личный сервер", "Personal server")}</span><h1 className="max-w-md !text-4xl leading-tight sm:!text-5xl">{t("Подключение под вашим контролем.", "Your connection, in your control.")}</h1><p className="muted max-w-md leading-relaxed">{t("Настройте сервер, подключите устройства и управляйте доступом в одном месте.", "Set up your server, connect devices and manage access in one place.")}</p><p className="muted text-xs">Xray · sing-box · {t("На вашем сервере", "Self-hosted")}</p></div><Card className="space-y-6"><div><h2>{t("Войти в панель", "Sign in to your panel")}</h2><p className="muted mt-2 text-sm">{t("При первом входе используйте данные установщика.", "Use the installer credentials for your first sign-in.")}</p></div><form onSubmit={submit} className="space-y-5"><Field label={t("Имя пользователя", "Username")}><input className="input" autoComplete="username" value={username} onChange={(event) => setUsername(event.target.value)} required autoFocus /></Field><Field label={t("Пароль", "Password")}><div className="relative"><input id="login-password" aria-label={t("Пароль", "Password")} className="input pr-14" autoComplete="current-password" type={show ? "text" : "password"} value={password} onChange={(event) => setPassword(event.target.value)} required /><button type="button" className="absolute right-0 top-0 flex h-11 w-11 items-center justify-center muted" aria-label={t("Показать или скрыть пароль", "Show or hide password")} onClick={() => setShow(!show)}>{show ? <EyeOff size={18} /> : <Eye size={18} />}</button></div></Field>{error && <p role="alert" className="notice notice-danger">{error}</p>}<Button type="submit" loading={busy} icon={ArrowRight} className="w-full">{t("Войти", "Sign in")}</Button></form></Card></main></div>;
}
