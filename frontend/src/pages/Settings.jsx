import React, { useCallback, useEffect, useState } from "react";
import { Check, Download, Globe, KeyRound, Moon, RefreshCw, RotateCcw, Sun, Terminal } from "lucide-react";
import toast from "react-hot-toast";
import api, { apiError, statsApi } from "../utils/api";
import { useI18n, usePreferences } from "../store";
import { Badge, Button, Card, EmptyState, ErrorState, Field, Loading, Modal, PageHeader } from "../components/ui";

const fetchVersion = () => api.get("/api/system/version");
const fetchCertificate = () => api.get("/api/system/cert/status");
const fetchSystem = () => statsApi.system();
function RemoteCard({ title, fetcher, children }) {
  const { t } = useI18n();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const load = useCallback(async () => {
    setLoading(true); setError("");
    try { const result = await fetcher(); setData(result.data); }
    catch (failure) { setError(apiError(failure)); }
    finally { setLoading(false); }
  }, [fetcher]);
  useEffect(() => { load(); }, [load]);
  return <Card className="space-y-5"><div className="flex items-center justify-between gap-3"><h2 className="text-base font-semibold">{title}</h2><Button variant="ghost" icon={RefreshCw} onClick={load} disabled={loading} aria-label={t("Обновить", "Refresh")} /></div>{loading ? <Loading label={t("Получаем сведения", "Loading details")} /> : error ? <ErrorState message={error} onRetry={load} /> : data ? children(data) : <EmptyState title={t("Нет данных", "No data")} action={<Button variant="secondary" onClick={load}>{t("Повторить", "Retry")}</Button>} />}</Card>;
}
function Detail({ label, value }) {
  return <div className="flex flex-wrap items-baseline justify-between gap-x-6 gap-y-1 border-b border-[var(--border)] py-3 last:border-0"><dt className="text-sm text-[var(--muted)]">{label}</dt><dd className="min-w-0 break-words text-right text-sm">{value ?? "—"}</dd></div>;
}
function Service({ service, label }) {
  const { t } = useI18n();
  const [active, setActive] = useState(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const check = useCallback(async () => {
    setLoading(true); setError("");
    try { const { data } = await api.get(`/api/system/${service}/status`); setActive(data.active); }
    catch (failure) { setError(apiError(failure)); }
    finally { setLoading(false); }
  }, [service]);
  useEffect(() => { check(); }, [check]);
  async function restart() {
    if (!window.confirm(t(`Перезапустить ${label}? Активные подключения могут прерваться.`, `Restart ${label}? Active connections may be interrupted.`))) return;
    setBusy(true); setError("");
    try {
      const { data } = await api.post(`/api/system/${service}/restart`);
      if (data.status !== "restarted") throw new Error(t("Сервер не подтвердил перезапуск.", "The server did not confirm the restart."));
      toast.success(t(`${label} перезапущен`, `${label} restarted`)); await check();
    } catch (failure) { setError(failure.response ? apiError(failure) : failure.message); }
    finally { setBusy(false); }
  }
  return <div className="space-y-3 border-b border-[var(--border)] py-4 last:border-0"><div className="flex flex-wrap items-center justify-between gap-3"><div className="flex items-center gap-3"><span className="font-medium">{label}</span><Badge variant={active === true ? "success" : "neutral"}>{loading ? t("Проверяем", "Checking") : active === true ? t("Запущен", "Running") : active === false ? t("Остановлен", "Stopped") : t("Неизвестно", "Unknown")}</Badge></div><Button variant="secondary" icon={RotateCcw} loading={busy} disabled={loading} onClick={restart}>{t("Перезапустить", "Restart")}</Button></div>{error && <ErrorState message={error} onRetry={check} />}</div>;
}
function PasswordForm() {
  const { t } = useI18n();
  const [values, setValues] = useState({ current: "", next: "", confirm: "" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);
  const change = (key) => (event) => { setSaved(false); setValues((previous) => ({ ...previous, [key]: event.target.value })); };
  async function submit(event) {
    event.preventDefault(); setSaved(false); setError("");
    if (values.next !== values.confirm) { setError(t("Новые пароли не совпадают.", "The new passwords do not match.")); return; }
    if (new TextEncoder().encode(values.next).length > 72) { setError(t("Пароль должен занимать не более 72 байт UTF-8.", "Password must be no more than 72 UTF-8 bytes.")); return; }
    setBusy(true);
    try {
      await api.post("/api/auth/password", { current_password: values.current, new_password: values.next }, { skipAuthRedirect: true });
      setValues({ current: "", next: "", confirm: "" }); setSaved(true);
    } catch (failure) { setError(apiError(failure)); }
    finally { setBusy(false); }
  }
  return <Card className="space-y-5"><div><h2 className="text-base font-semibold">{t("Пароль входа", "Sign-in password")}</h2><p className="mt-1 text-sm text-[var(--muted)]">{t("Изменяется пароль текущего аккаунта панели. Ключи VPN остаются прежними.", "Changes your current panel account password. VPN credentials stay the same.")}</p></div><form className="space-y-4" onSubmit={submit}>
    <Field label={t("Текущий пароль", "Current password")}><input className="input" type="password" required autoComplete="current-password" value={values.current} onChange={change("current")} /></Field>
    <Field label={t("Новый пароль", "New password")} hint={t("Не менее 12 символов, не более 72 байт UTF-8", "At least 12 characters, at most 72 UTF-8 bytes")}><input className="input" type="password" required minLength={12} autoComplete="new-password" value={values.next} onChange={change("next")} /></Field>
    <Field label={t("Повторите новый пароль", "Confirm new password")}><input className="input" type="password" required minLength={12} autoComplete="new-password" value={values.confirm} onChange={change("confirm")} /></Field>
    {error && <ErrorState message={error} />}{saved && <p role="status" className="text-sm text-[var(--success)]">{t("Пароль изменён.", "Password changed.")}</p>}
    <Button type="submit" icon={KeyRound} loading={busy}>{t("Сменить пароль", "Change password")}</Button>
  </form></Card>;
}
function Backup() {
  const { t } = useI18n();
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  async function create() {
    setBusy(true); setError(""); setResult(null);
    try {
      const { data } = await api.post("/api/system/backup");
      if (data.status !== "backup_complete" || data.verified !== true) throw new Error(t("Проверка резервной копии не подтверждена.", "Backup verification was not confirmed."));
      setResult(data);
    } catch (failure) { setError(failure.response ? apiError(failure) : failure.message); }
    finally { setBusy(false); }
  }
  return <Card className="space-y-5"><h2 className="text-base font-semibold">{t("Резервная копия", "Backup")}</h2><p className="text-sm text-[var(--muted)]">{t("Создаётся согласованный снимок SQLite и архив настроек с проверкой восстановления. Копия сохраняется на сервере в BACKUP_DIR (по умолчанию /data/backups), а не скачивается в браузер. Архив содержит секреты; храните его приватно.", "Creates a consistent SQLite snapshot and a configuration archive with restoration verification. It is saved on the server in BACKUP_DIR (default /data/backups), not downloaded to this browser. Archives contain secrets; keep them private.")}</p>{error && <ErrorState message={error} />}{result && <div className="notice space-y-2" role="status"><div className="flex items-center gap-2 text-[var(--success)]"><Check size={16} /><span>{t("Копия создана и проверена", "Backup created and verified")}</span></div><p className="break-all font-mono text-xs">{result.archive}</p><p className="text-sm text-[var(--muted)]">{(result.size_bytes / 1024).toFixed(1)} KiB</p></div>}<Button icon={Download} loading={busy} onClick={create}>{t("Создать копию на сервере", "Create server backup")}</Button></Card>;
}

export default function Settings() {
  const { t } = useI18n();
  const { theme, setTheme, language, setLanguage } = usePreferences();
  const [logs, setLogs] = useState(null);
  const [logOpen, setLogOpen] = useState(false);
  const [logBusy, setLogBusy] = useState(false);
  const [logError, setLogError] = useState("");
  async function loadLogs() {
    setLogOpen(true); setLogBusy(true); setLogError("");
    try { const { data } = await api.get("/api/system/logs/fvpn-backend?lines=100"); setLogs(typeof data === "string" ? data : JSON.stringify(data, null, 2)); }
    catch (failure) { setLogError(apiError(failure)); }
    finally { setLogBusy(false); }
  }
  return <div className="page space-y-6">
    <PageHeader title={t("Настройки", "Settings")} description={t("Внешний вид, безопасность и обслуживание", "Appearance, security and maintenance")} />
    <Card className="space-y-5"><div><h2 className="text-base font-semibold">{t("Сделайте панель удобной", "Make the panel yours")}</h2><p className="mt-1 text-sm text-[var(--muted)]">{t("Язык и тема сохраняются в этом браузере.", "Language and theme are saved in this browser.")}</p></div><div className="grid gap-5 sm:grid-cols-2"><fieldset className="space-y-3"><legend className="text-sm font-medium">{t("Оформление", "Appearance")}</legend><div className="flex flex-wrap gap-2"><Button variant={theme === "light" ? "primary" : "secondary"} icon={Sun} aria-pressed={theme === "light"} onClick={() => setTheme("light")}>{t("Светлое", "Light")}</Button><Button variant={theme === "dark" ? "primary" : "secondary"} icon={Moon} aria-pressed={theme === "dark"} onClick={() => setTheme("dark")}>{t("Тёмное", "Dark")}</Button></div></fieldset><fieldset className="space-y-3"><legend className="text-sm font-medium">{t("Язык", "Language")}</legend><div className="flex flex-wrap gap-2"><Button variant={language === "ru" ? "primary" : "secondary"} icon={Globe} aria-pressed={language === "ru"} onClick={() => setLanguage("ru")}>Русский</Button><Button variant={language === "en" ? "primary" : "secondary"} aria-pressed={language === "en"} onClick={() => setLanguage("en")}>English</Button></div></fieldset></div></Card>
    <div className="grid items-start gap-5 xl:grid-cols-2">
      <PasswordForm />
      <Backup />
      <Card className="space-y-5"><div><h2 className="text-base font-semibold">{t("Службы подключения", "Connection services")}</h2><p className="mt-1 text-sm text-[var(--muted)]">{t("Перезапуск может прервать текущие подключения.", "Restarting may interrupt active connections.")}</p></div><div><Service service="xray" label="Xray" /><Service service="singbox" label="sing-box" /></div><Button variant="secondary" icon={Terminal} onClick={loadLogs}>{t("Открыть журнал backend", "View backend logs")}</Button></Card>
      <RemoteCard title={t("Сертификат панели", "Panel certificate")} fetcher={fetchCertificate}>{(data) => <><dl><Detail label={t("Домен", "Domain")} value={data.domain} /><Detail label={t("Сертификат прочитан", "Certificate readable")} value={data.valid ? t("Да", "Yes") : t("Нет", "No")} /><Detail label={t("Выдан", "Issued")} value={data.not_before} /><Detail label={t("Действует до", "Expires")} value={data.not_after} /></dl>{data.error && <p className="text-sm text-[var(--danger)]">{data.error}</p>}<p className="text-sm text-[var(--muted)]">{t("Даты не подтверждают доверие браузера или соответствие домену. Продление Let's Encrypt выполняет таймер Certbot на хосте; панель не запускает его из контейнера. Для самоподписанного сертификата нужна ручная замена.", "Dates do not prove browser trust or hostname validity. The host Certbot timer handles Let's Encrypt renewal; the panel does not launch it from a container. Replace self-signed certificates manually.")}</p></>}</RemoteCard>
      <RemoteCard title={t("Версии компонентов", "Component versions")} fetcher={fetchVersion}>{(data) => <dl><Detail label="FVpn" value={data.fvpn || data.uniproxy} /><Detail label="Xray" value={data.xray} /><Detail label="sing-box" value={data.sing_box} /></dl>}</RemoteCard>
      <RemoteCard title={t("Ресурсы сервера", "Server resources")} fetcher={fetchSystem}>{(data) => <><dl><Detail label={t("Ядер CPU", "CPU cores")} value={data.cpu_cores} /><Detail label={t("Память", "Memory")} value={data.ram ? `${data.ram.used_gb} / ${data.ram.total_gb} GB · ${data.ram.pct}%` : "—"} /><Detail label={t("Диск контейнера", "Container disk")} value={data.disk ? `${data.disk.used_gb} / ${data.disk.total_gb} GB · ${data.disk.pct}%` : "—"} /><Detail label={t("Время работы ОС", "OS uptime")} value={data.uptime_hours == null ? "—" : `${data.uptime_hours} h`} /></dl><p className="text-xs text-[var(--muted)]">{t("Измерения видны из контейнера backend. Это не учёт пользовательского VPN-трафика.", "Measurements are visible from the backend container. They do not account for individual VPN traffic.")}</p></>}</RemoteCard>
      <Card className="space-y-4 xl:col-span-2"><h2 className="text-base font-semibold">{t("Возможности FVpn", "About FVpn")}</h2><p className="text-sm leading-relaxed text-[var(--muted)]">{t("Локальные конфигурации: VLESS Reality, Shadowsocks, Hysteria2, Trojan, TUIC, ShadowTLS и VMess. Поддержка зависит от клиентского приложения. WireGuard и SSH не доступны как управляемые пресеты; WireGuard исключён из экспорта. Учётные данные подключения общие для подписок. Персональные квоты, история и реальный учёт VPN-трафика не реализованы.", "Local configurations: VLESS Reality, Shadowsocks, Hysteria2, Trojan, TUIC, ShadowTLS and VMess. Support depends on the client application. WireGuard and SSH are not managed presets; WireGuard is excluded from exports. Connection credentials are shared between subscriptions. Individual quotas, traffic history and actual VPN usage accounting are not implemented.")}</p><a className="inline-flex min-h-11 items-center text-sm font-medium text-[var(--accent)] underline underline-offset-4" href="https://github.com/franklin-lol/FVpn" target="_blank" rel="noopener noreferrer">{t("Репозиторий и документация", "Repository and documentation")}</a></Card>
    </div>
    {logOpen && <Modal title={t("Журнал backend", "Backend logs")} onClose={() => setLogOpen(false)}><div className="space-y-4">{logBusy ? <Loading label={t("Читаем журнал", "Loading logs")} /> : logError ? <ErrorState message={logError} onRetry={loadLogs} /> : logs ? <pre className="max-h-96 overflow-auto whitespace-pre-wrap break-words rounded-xl bg-[var(--surface-soft)] p-4 font-mono text-xs">{logs}</pre> : <EmptyState title={t("Записей пока нет", "No log entries yet")} action={<Button variant="secondary" onClick={loadLogs}>{t("Обновить", "Refresh")}</Button>} />}<p className="text-xs text-[var(--muted)]">{t("Не публикуйте журнал без проверки на личные данные и секреты.", "Review logs for personal data and secrets before sharing.")}</p></div></Modal>}
  </div>;
}
