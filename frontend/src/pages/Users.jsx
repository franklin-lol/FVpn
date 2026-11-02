import React, { useCallback, useEffect, useState } from "react";
import { ArrowLeft, ArrowRight, Ban, Check, ExternalLink, Link2, Plus, QrCode, RefreshCw, Trash2, Users as UsersIcon } from "lucide-react";
import QRCode from "react-qr-code";
import toast from "react-hot-toast";
import { apiError, subsApi, usersApi } from "../utils/api";
import { getSubscriptionImportUrl } from "../utils/subscriptionImport";
import { useAuthStore, useI18n } from "../store";
import { Badge, Button, Card, CopyButton, EmptyState, ErrorState, Field, Loading, Modal, PageHeader } from "../components/ui";

const PAGE_SIZE = 20;
const FORMATS = [{ value: "base64", label: "Hiddify / Streisand" }, { value: "v2rayng", label: "v2rayNG" }, { value: "shadowrocket", label: "Shadowrocket" }, { value: "clash", label: "Clash / Mihomo" }, { value: "singbox", label: "sing-box (JSON)" }, { value: "hiddify", label: "Hiddify (JSON)" }];

function AddUser({ onClose, onCreated }) {
  const { t } = useI18n();
  const [form, setForm] = useState({ username: "", password: "", email: "", expire_at: "", is_admin: false });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const change = (key) => (event) => setForm((previous) => ({ ...previous, [key]: event.target.value }));
  async function submit(event) {
    event.preventDefault(); setError("");
    if (new TextEncoder().encode(form.password).length > 72) { setError(t("Пароль должен занимать не более 72 байт UTF-8.", "Password must be no more than 72 UTF-8 bytes.")); return; }
    setBusy(true);
    try {
      await usersApi.create({ username: form.username.trim(), password: form.password, email: form.email.trim() || null, is_admin: form.is_admin, expire_at: form.expire_at ? `${form.expire_at}T23:59:59` : null });
      toast.success(t("Пользователь создан", "User created")); await onCreated(); onClose();
    } catch (failure) { setError(apiError(failure)); }
    finally { setBusy(false); }
  }
  return <Modal title={t("Добавить пользователя", "Add a user")} onClose={() => { if (!busy) onClose(); }}><form className="space-y-5" onSubmit={submit}>
    <p className="text-sm text-[var(--muted)]">{t("Создайте аккаунт, затем выдайте ему ссылку подключения.", "Create an account, then share its connection link.")}</p>
    <Field label={t("Имя пользователя", "Username")}><input className="input" required autoFocus maxLength={64} autoComplete="off" value={form.username} onChange={change("username")} placeholder="alex" /></Field>
    <Field label={t("Пароль панели", "Panel password")} hint={t("Не менее 12 символов. Ссылка подключения используется отдельно от пароля.", "At least 12 characters. Connection links are separate from this password.")}><input className="input" type="password" required minLength={12} autoComplete="new-password" value={form.password} onChange={change("password")} /></Field>
    <details className="rounded-xl border border-[var(--border)] p-4"><summary className="cursor-pointer text-sm font-medium">{t("Дополнительные настройки", "Advanced settings")}</summary><div className="mt-4 space-y-4">
      <Field label={t("Электронная почта", "Email")}><input className="input" type="email" maxLength={255} value={form.email} onChange={change("email")} placeholder={t("Необязательно", "Optional")} /></Field>
      <Field label={t("Срок выдачи конфигурации", "Configuration access expiry")} hint={t("До конца выбранного дня по UTC. Срок ограничивает загрузку подписки; уже импортированные ключи VPN не отзываются.", "Through the selected UTC day. Expiry blocks subscription downloads; imported VPN credentials are not revoked.")}><input className="input" type="date" value={form.expire_at} onChange={change("expire_at")} /></Field>
      <label className="flex min-h-11 items-center gap-3 text-sm"><input className="h-5 w-5 accent-[var(--accent)]" type="checkbox" checked={form.is_admin} onChange={(event) => setForm((previous) => ({ ...previous, is_admin: event.target.checked }))} />{t("Администратор панели", "Panel administrator")}</label>
      {form.is_admin && <p className="notice">{t("Администратор получает доступ ко всем серверам, пользователям и секретам подключения.", "Administrators can access all servers, users and connection secrets.")}</p>}
    </div></details>
    {error && <ErrorState message={error} />}
    <Button type="submit" icon={Plus} loading={busy} className="w-full">{t("Добавить пользователя", "Add user")}</Button>
  </form></Modal>;
}

function Subscriptions({ user, onClose }) {
  const { t } = useI18n();
  const [subscriptions, setSubscriptions] = useState([]);
  const [format, setFormat] = useState("hiddify");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [mutationError, setMutationError] = useState("");
  const [busy, setBusy] = useState("");
  const [qrId, setQrId] = useState(null);
  const load = useCallback(async () => {
    setLoading(true); setError("");
    try { const { data } = await subsApi.list(); setSubscriptions(data.filter((subscription) => subscription.user_id === user.id)); }
    catch (failure) { setError(apiError(failure)); }
    finally { setLoading(false); }
  }, [user.id]);
  useEffect(() => { load(); }, [load]);
  async function create(event) {
    event.preventDefault(); setBusy("create"); setMutationError("");
    try {
      const { data } = await subsApi.create({ format, user_id: user.id });
      if (data.user_id !== user.id) throw new Error(t("Сервер вернул неверного владельца подписки. Обновите страницу и проверьте подписки.", "The server returned the wrong subscription owner. Refresh and review subscriptions."));
      await load(); setQrId(data.id);
    } catch (failure) { setMutationError(failure.response ? apiError(failure) : failure.message); }
    finally { setBusy(""); }
  }
  async function remove(subscription) {
    if (!window.confirm(t("Удалить ссылку? По ней больше нельзя будет загрузить настройки. Уже импортированные ключи VPN останутся действовать.", "Delete this link? It will no longer download configurations. Previously imported VPN credentials remain valid."))) return;
    setBusy(`delete-${subscription.id}`); setMutationError("");
    try { await subsApi.delete(subscription.id); await load(); }
    catch (failure) { setMutationError(apiError(failure)); }
    finally { setBusy(""); }
  }
  return <Modal title={t(`Подключить: ${user.username}`, `Connect: ${user.username}`)} onClose={() => { if (!busy) onClose(); }} wide>
    <div className="space-y-5">
      <p className="text-sm text-[var(--muted)]">{t("Выберите приложение и создайте личную ссылку. Отправьте пользователю страницу подключения: там есть инструкция, QR и импорт.", "Choose an app and create a personal link. Share the connection page with the user for instructions, QR and import.")}</p>
      {(!user.is_active || user.is_expired) && <p className="notice">{t("Загрузка настроек для этого аккаунта отключена или срок истёк. Существующие ключи VPN это не отзывает.", "Configuration downloads for this account are disabled or expired. Existing VPN credentials are not revoked.")}</p>}
      <form className="flex flex-col gap-3 sm:flex-row sm:items-end" onSubmit={create}><Field label={t("Приложение или формат", "App or format")} className="flex-1"><select className="input" value={format} onChange={(event) => setFormat(event.target.value)}>{FORMATS.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}</select></Field><Button type="submit" icon={Plus} loading={busy === "create"} disabled={!!busy || loading || !!error || !user.is_active || user.is_expired}>{t("Создать ссылку", "Create link")}</Button></form>
      {mutationError && <ErrorState message={mutationError} />}
      {loading ? <Loading label={t("Загружаем ссылки", "Loading links")} /> : error ? <ErrorState message={error} onRetry={load} /> : subscriptions.length === 0 ? <EmptyState icon={Link2} title={t("Пока нет ссылок", "No links yet")} description={t("Выберите приложение выше и создайте первую ссылку.", "Choose an app above and create the first link.")} /> : <div className="space-y-4">{subscriptions.map((subscription) => {
        const connectionLink = subscription.connect_url || new URL(`/s/${encodeURIComponent(subscription.token)}`, subscription.url).toString();
        const importUrl = getSubscriptionImportUrl(subscription);
        return <Card key={subscription.id} className="space-y-4 !bg-[var(--surface-soft)]"><div className="flex flex-wrap items-center justify-between gap-3"><Badge>{FORMATS.find((item) => item.value === subscription.format)?.label || subscription.format}</Badge><Button variant="ghost" icon={Trash2} aria-label={t("Удалить ссылку", "Delete link")} disabled={!!busy} loading={busy === `delete-${subscription.id}`} onClick={() => remove(subscription)} /></div>
          <Field label={t("Подписка для приложения", "App subscription URL")}><input className="input font-mono text-xs" readOnly value={importUrl} onFocus={(event) => event.target.select()} /></Field>
          <div className="flex flex-wrap gap-2"><CopyButton text={importUrl}>{t("Копировать для приложения", "Copy for app")}</CopyButton><Button variant="secondary" icon={QrCode} aria-expanded={qrId === subscription.id} onClick={() => setQrId(qrId === subscription.id ? null : subscription.id)}>{t("QR для приложения", "App QR code")}</Button></div>
          {qrId === subscription.id && <figure className="space-y-3 text-center"><div className="mx-auto w-fit max-w-full rounded-xl bg-white p-4"><QRCode value={importUrl} size={176} style={{ maxWidth: "100%", height: "auto" }} /></div><figcaption className="text-xs text-[var(--muted)]">{t("Сканируйте в VPN-приложении, чтобы добавить подписку", "Scan inside your VPN app to add the subscription")}</figcaption></figure>}
          <div className="space-y-3 border-t border-[var(--border)] pt-4"><p className="text-sm text-[var(--muted)]">{t("Нужна инструкция? Отправьте пользователю страницу подключения.", "Need instructions? Share the connection guide with the user.")}</p><div className="flex flex-wrap gap-2"><CopyButton text={connectionLink}>{t("Копировать инструкцию", "Copy guide link")}</CopyButton><a className="btn btn-secondary" href={connectionLink} target="_blank" rel="noopener noreferrer">{t("Открыть инструкцию", "Open guide")}<ExternalLink size={16} /></a></div></div>
          <details><summary className="cursor-pointer text-sm">{t("Для опытных пользователей: исходный формат", "Advanced: original format")}</summary><div className="mt-3 space-y-3"><p className="break-all font-mono text-xs text-[var(--muted)]">{subscription.url}</p><CopyButton text={subscription.url}>{t("Копировать исходную подписку", "Copy original subscription")}</CopyButton></div></details>
        </Card>;
      })}</div>}
      <p className="text-xs text-[var(--muted)]">{t("Ссылка даёт доступ к настройкам и содержит секретный токен. Делитесь только с получателем. Ключи протоколов общие, поэтому удаление ссылки не отключает ранее настроенный VPN.", "A link grants configuration access and contains a secret token. Share it only with the recipient. Protocol credentials are shared, so deleting a link does not disable an already configured VPN.")}</p>
    </div>
  </Modal>;
}

export default function Users() {
  const { t, language } = useI18n();
  const currentUsername = useAuthStore((state) => state.user);
  const [users, setUsers] = useState([]);
  const [page, setPage] = useState(0);
  const [hasNext, setHasNext] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");
  const [addOpen, setAddOpen] = useState(false);
  const [selectedUser, setSelectedUser] = useState(null);
  const load = useCallback(async () => {
    setLoading(true); setError("");
    try { const { data } = await usersApi.list(page * PAGE_SIZE, PAGE_SIZE + 1); setUsers(data.slice(0, PAGE_SIZE)); setHasNext(data.length > PAGE_SIZE); }
    catch (failure) { setError(apiError(failure)); }
    finally { setLoading(false); }
  }, [page]);
  useEffect(() => { load(); }, [load]);
  async function mutate(user, remove = false) {
    const prompt = remove ? t(`Удалить аккаунт «${user.username}» и ссылки? Уже импортированные ключи VPN останутся действовать.`, `Delete “${user.username}” and its links? Previously imported VPN credentials remain valid.`) : user.is_active ? t(`Отключить вход и загрузку подписок для «${user.username}»? Уже импортированный VPN останется доступен.`, `Disable sign-in and subscription downloads for “${user.username}”? Previously imported VPN access remains available.`) : t(`Включить аккаунт «${user.username}»?`, `Enable “${user.username}”?`);
    if (user.username === currentUsername || !window.confirm(prompt)) return;
    setBusy(`${remove ? "delete" : "toggle"}-${user.id}`);
    try {
      if (remove) await usersApi.delete(user.id); else await usersApi.update(user.id, { is_active: !user.is_active });
      if (remove && users.length === 1 && page > 0) setPage((previous) => previous - 1); else await load();
    } catch (failure) { toast.error(apiError(failure)); }
    finally { setBusy(""); }
  }
  const date = (value) => value ? new Date(value.endsWith("Z") || /[+-]\d\d:\d\d$/.test(value) ? value : value + "Z").toLocaleDateString(language === "ru" ? "ru-RU" : "en-US", { timeZone: "UTC" }) : t("Без срока", "No expiry");
  return <div className="page space-y-6">
    <PageHeader title={t("Пользователи", "Users")} description={t("Аккаунты панели и ссылки подключения", "Panel accounts and connection links")} actions={<><Button variant="secondary" icon={RefreshCw} onClick={load} disabled={loading || !!busy}>{t("Обновить", "Refresh")}</Button><Button icon={Plus} onClick={() => setAddOpen(true)}>{t("Добавить пользователя", "Add user")}</Button></>} />
    <p className="notice">{t("Аккаунт управляет входом и загрузкой подписки. Ключи VPN общие: отключение аккаунта или удаление ссылки не отзывает уже импортированные настройки. Персональные квоты не применяются.", "An account controls panel sign-in and subscription downloads. VPN credentials are shared: disabling an account or deleting a link does not revoke imported configurations. Individual quotas are not enforced.")}</p>
    {loading ? <Loading label={t("Загружаем пользователей", "Loading users")} /> : error ? <ErrorState message={error} onRetry={load} /> : !users.length ? <EmptyState icon={UsersIcon} title={page ? t("На этой странице нет пользователей", "No users on this page") : t("Добавьте первого пользователя", "Add your first user")} description={t("После создания выдайте ему ссылку подключения.", "After creating an account, share its connection link.")} action={page ? <Button variant="secondary" onClick={() => setPage(0)}>{t("К первой странице", "First page")}</Button> : <Button icon={Plus} onClick={() => setAddOpen(true)}>{t("Добавить пользователя", "Add user")}</Button>} /> : <div className="grid gap-4 xl:grid-cols-2">{users.map((user) => {
      const self = user.username === currentUsername;
      return <Card key={user.id} className="space-y-5"><div className="flex items-start justify-between gap-3"><div className="min-w-0"><h2 className="break-words text-base font-semibold">{user.username}{self && <span className="ml-2 text-sm font-normal text-[var(--muted)]">{t("это вы", "you")}</span>}</h2>{user.email && <p className="mt-1 break-all text-sm text-[var(--muted)]">{user.email}</p>}</div><Badge variant={!user.is_active || user.is_expired ? "neutral" : "success"}>{!user.is_active ? t("Отключён", "Disabled") : user.is_expired ? t("Срок истёк", "Expired") : t("Активен", "Active")}</Badge></div>
        <div className="flex flex-wrap items-center gap-2">{user.is_admin && <Badge variant="accent">{t("Администратор", "Administrator")}</Badge>}<p className="text-sm text-[var(--muted)]">{t("Срок подписки", "Subscription expiry")}: {date(user.expire_at)}</p></div>
        <div className="flex flex-wrap gap-2 border-t border-[var(--border)] pt-4"><Button icon={Link2} onClick={() => setSelectedUser(user)}>{t("Подключить устройство", "Connect a device")}</Button><Button variant="secondary" icon={user.is_active ? Ban : Check} disabled={!!busy || self} loading={busy === `toggle-${user.id}`} onClick={() => mutate(user)}>{user.is_active ? t("Отключить", "Disable") : t("Включить", "Enable")}</Button><Button variant="ghost" icon={Trash2} disabled={!!busy || self} loading={busy === `delete-${user.id}`} aria-label={t(`Удалить ${user.username}`, `Delete ${user.username}`)} onClick={() => mutate(user, true)} /></div>
        {self && <p className="text-xs text-[var(--muted)]">{t("Вы не можете отключить или удалить себя в этом интерфейсе.", "You cannot disable or delete yourself in this interface.")}</p>}
      </Card>;
    })}</div>}
    {(page > 0 || hasNext) && <nav className="flex items-center justify-between gap-3" aria-label={t("Страницы пользователей", "User pages")}><Button variant="secondary" icon={ArrowLeft} disabled={page === 0 || loading || !!busy} onClick={() => setPage((previous) => previous - 1)}>{t("Назад", "Previous")}</Button><span className="text-sm text-[var(--muted)]">{t("Страница", "Page")} {page + 1}</span><Button variant="secondary" icon={ArrowRight} disabled={!hasNext || loading || !!busy} onClick={() => setPage((previous) => previous + 1)}>{t("Далее", "Next")}</Button></nav>}
    {addOpen && <AddUser onClose={() => setAddOpen(false)} onCreated={load} />}
    {selectedUser && <Subscriptions user={selectedUser} onClose={() => setSelectedUser(null)} />}
  </div>;
}
