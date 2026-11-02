import React, { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ArrowLeft, ArrowRight, Check, KeyRound, Server, ShieldCheck } from "lucide-react";
import api, { apiError } from "../utils/api";
import { useI18n } from "../store";
import { Badge, Button, Card, ErrorState, Field, Loading } from "../components/ui";
import { PreferencesControls } from "../components/Layout";
import useRemote from "../utils/useRemote";

export default function Setup() {
  const { t } = useI18n();
  const navigate = useNavigate();
  const { data, loading, error, reload } = useRemote(async () => (await api.get("/api/setup")).data);
  const [step, setStep] = useState(0);
  const [current, setCurrent] = useState("");
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [nodeId, setNodeId] = useState("");
  const [preset, setPreset] = useState("recommended");
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState("");
  const currentStep = data?.password_changed ? Math.max(1, step) : 0;
  const selected = data?.nodes.find((node) => node.id === Number(nodeId || data.local_node_id || data.nodes[0]?.id));
  const change = async (event) => {
    event.preventDefault(); setFailure("");
    if (password !== confirmation) { setFailure(t("Пароли не совпадают.", "Passwords do not match.")); return; }
    if (new TextEncoder().encode(password).length > 72) { setFailure(t("Пароль должен занимать не больше 72 байт.", "Password must be at most 72 bytes.")); return; }
    setBusy(true);
    try { await api.post("/api/auth/password", { current_password: current, new_password: password }, { skipAuthRedirect: true }); setCurrent(""); setPassword(""); setConfirmation(""); setStep(1); reload(); }
    catch (error) { setFailure(apiError(error)); }
    finally { setBusy(false); }
  };
  const finish = async () => {
    if (!selected) return;
    setBusy(true); setFailure("");
    try { await api.post("/api/setup/complete", { node_id: selected.id, preset: selected.local ? preset : "existing" }); navigate("/users", { replace: true }); }
    catch (error) { setFailure(apiError(error)); }
    finally { setBusy(false); }
  };
  return <div className="min-h-dvh"><header className="mx-auto flex max-w-5xl items-center justify-between p-4 sm:p-6"><span className="flex items-center gap-2 font-semibold"><ShieldCheck size={24} className="text-accent" />FVpn</span><PreferencesControls /></header><main className="mx-auto max-w-3xl space-y-6 px-4 py-6 sm:py-10"><div className="space-y-3"><Badge variant="accent">{t("Первый запуск", "First run")}</Badge><h1>{t("Настройте один раз. Подключайтесь каждый день.", "Set up once. Connect every day.")}</h1><p className="muted">{t("Три шага до первого подключения. Тонкая настройка останется доступна в панели.", "Three steps to your first connection. Fine-tune everything later in the panel.")}</p></div>{loading ? <Loading /> : error ? <ErrorState message={error} onRetry={reload} /> : <><ol className="flex gap-2 sm:gap-6">{[[KeyRound, t("Пароль", "Password")], [Server, t("Сервер", "Server")], [ShieldCheck, t("Подключение", "Connection")]].map(([Icon, label], index) => <li key={label} className="flex flex-1 items-center gap-2 border-b-2 pb-4 text-sm" style={{ borderColor: index <= currentStep ? "var(--accent)" : "var(--border)", color: index <= currentStep ? "var(--accent)" : "var(--muted)" }}><Icon size={18} className="shrink-0" /><span>{label}</span></li>)}</ol>{failure && <ErrorState message={failure} />}
    {currentStep === 0 && <Card className="space-y-5"><div><h2>{t("Задайте свой пароль", "Choose your own password")}</h2><p className="muted mt-2 text-sm">{t("Замените пароль из установщика. Данные в .env останутся без изменений.", "Replace the installer password. Your .env settings stay intact.")}</p></div><form onSubmit={change} className="space-y-5"><Field label={t("Текущий пароль", "Current password")}><input className="input" type="password" autoComplete="current-password" value={current} onChange={(e) => setCurrent(e.target.value)} required /></Field><Field label={t("Новый пароль", "New password")} hint={t("От 12 символов, до 72 байт.", "At least 12 characters, at most 72 bytes.")}><input className="input" type="password" autoComplete="new-password" minLength={12} value={password} onChange={(e) => setPassword(e.target.value)} required /></Field><Field label={t("Повторите новый пароль", "Confirm new password")}><input className="input" type="password" autoComplete="new-password" minLength={12} value={confirmation} onChange={(e) => setConfirmation(e.target.value)} required /></Field><Button type="submit" loading={busy} icon={ArrowRight} className="w-full sm:w-auto">{t("Сохранить и продолжить", "Save and continue")}</Button></form></Card>}
    {currentStep === 1 && <Card className="space-y-5"><div><h2>{t("Выберите сервер", "Choose your server")}</h2><p className="muted mt-2 text-sm">{t("Установщик уже подготовил локальный сервер. Используйте его для быстрого начала.", "The installer prepares the local server. Use it for a quick start.")}</p></div>{data.nodes.length ? <Field label={t("Сервер подключения", "Connection server")}><select className="input" value={selected?.id || ""} onChange={(e) => { setNodeId(e.target.value); setPreset("recommended"); }}>{data.nodes.map((node) => <option key={node.id} value={node.id}>{node.name} · {node.host}{node.local ? ` · ${t("этот сервер", "this server")}` : ""}</option>)}</select></Field> : <div className="notice"><p>{t("Локальный сервер ещё не создан. Проверьте состояние backend и конфигурацию установщика либо добавьте свой сервер.", "The local server is not ready. Check the backend and installer settings, or add your own server.")}</p><Link to="/nodes" className="btn btn-secondary mt-4">{t("Добавить сервер", "Add server")}</Link><Button variant="ghost" onClick={reload}>{t("Проверить снова", "Check again")}</Button></div>}{selected && !selected.local && <p className="notice">{t("Удалённому серверу требуется ручное применение конфигурации. Этот шаг использует его существующие подключения.", "A remote server requires manual configuration delivery. This step uses its existing connections.")}</p>}<div className="flex flex-wrap gap-3"><Button icon={ArrowRight} disabled={!selected} onClick={() => setStep(2)}>{t("Продолжить", "Continue")}</Button><Link className="btn btn-ghost" to="/nodes">{t("Добавить другой сервер", "Add another server")}</Link></div></Card>}
    {currentStep === 2 && <Card className="space-y-5"><div><h2>{t("Выберите способ подключения", "Choose a connection method")}</h2><p className="muted mt-2 text-sm">{selected?.name} · {selected?.host}</p></div>{selected?.local && <label className="flex cursor-pointer items-start gap-3 rounded-xl border border-line p-4"><input type="radio" name="preset" className="mt-1 accent-accent" checked={preset === "recommended"} onChange={() => setPreset("recommended")} /><div><span className="font-semibold">VLESS Reality <Badge variant="success">{t("Рекомендуем", "Recommended")}</Badge></span><p className="muted mt-2 text-sm">{t("TCP 443, без настройки сертификата клиента. Существующие ключи сохраняются.", "TCP 443, no client certificate setup. Existing keys are preserved.")}</p></div></label>}<details><summary>{t("У меня уже есть настройки", "I already have a configuration")}</summary><label className="mt-3 flex items-start gap-3 rounded-xl border border-line p-4"><input type="radio" name="preset" className="mt-1 accent-accent" checked={preset === "existing" || !selected?.local} onChange={() => setPreset("existing")} /><div><span className="font-semibold">{t("Использовать существующие подключения", "Use existing connections")}</span><p className="muted mt-2 text-sm">{t("Параметры протоколов можно изменить в разделе «Подключения».", "Edit protocol parameters in Connections.")}</p></div></label></details><div className="flex flex-wrap gap-3"><Button icon={Check} loading={busy} disabled={!selected} onClick={finish}>{t("Применить и перейти к устройствам", "Apply and connect devices")}</Button><Button variant="ghost" icon={ArrowLeft} disabled={busy} onClick={() => setStep(1)}>{t("Назад", "Back")}</Button></div></Card>}
  </>}</main></div>;
}
