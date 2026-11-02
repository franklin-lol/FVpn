import React, { useCallback, useEffect, useState } from "react";
import { ArrowUpRight, Plus, RefreshCw, Server, Trash2, Zap } from "lucide-react";
import { Link } from "react-router-dom";
import toast from "react-hot-toast";
import { nodesApi, apiError } from "../utils/api";
import { useI18n } from "../store";
import { Badge, Button, Card, EmptyState, ErrorState, Field, Loading, Modal, PageHeader } from "../components/ui";

function AddNode({ onClose, onCreated }) {
  const { t } = useI18n();
  const [form, setForm] = useState({ name: "", host: "", ssh_port: 22, ssh_user: "root", ssh_key: "", group: "" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const change = (key) => (event) => setForm((previous) => ({ ...previous, [key]: event.target.value }));
  async function submit(event) {
    event.preventDefault(); setBusy(true); setError("");
    try {
      await nodesApi.create({ ...form, name: form.name.trim(), host: form.host.trim(), ssh_port: Number(form.ssh_port), ssh_user: form.ssh_user.trim(), ssh_key: form.ssh_key.trim() || null, group: form.group.trim() || null });
      toast.success(t("Сервер добавлен", "Server added"));
      await onCreated(); onClose();
    } catch (failure) { setError(apiError(failure)); }
    finally { setBusy(false); }
  }
  return <Modal title={t("Добавить сервер", "Add a server")} onClose={() => { if (!busy) onClose(); }}>
    <form className="space-y-5" onSubmit={submit}>
      <p className="text-sm text-[var(--muted)]">{t("Сохраните адрес сервера, затем настройте подключение.", "Save the server address, then configure a connection.")}</p>
      <Field label={t("Название", "Name")} hint={t("Любое понятное вам название", "A name you will recognize")}><input className="input" autoFocus required maxLength={128} value={form.name} onChange={change("name")} placeholder={t("Мой сервер", "My server")} /></Field>
      <Field label={t("IP-адрес или домен", "IP address or domain")}><input className="input" required maxLength={253} value={form.host} onChange={change("host")} placeholder="203.0.113.10" autoCapitalize="none" spellCheck={false} /></Field>
      <details className="rounded-xl border border-[var(--border)] p-4">
        <summary className="cursor-pointer text-sm font-medium">{t("Дополнительно: SSH и группа", "Advanced: SSH and group")}</summary>
        <div className="mt-5 space-y-4">
          <p className="text-sm text-[var(--muted)]">{t("SSH нужен для удалённой установки Shadowsocks. Без ключа доступна ручная настройка.", "SSH is needed for remote Shadowsocks installation. Leave the key empty for manual setup.")}</p>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label={t("Порт SSH", "SSH port")}><input className="input" type="number" min={1} max={65535} required value={form.ssh_port} onChange={change("ssh_port")} /></Field>
            <Field label={t("Пользователь SSH", "SSH user")}><input className="input" required maxLength={64} value={form.ssh_user} onChange={change("ssh_user")} autoComplete="off" /></Field>
          </div>
          <Field label={t("Группа", "Group")}><input className="input" maxLength={64} value={form.group} onChange={change("group")} placeholder={t("Необязательно", "Optional")} /></Field>
          <Field label={t("Приватный ключ SSH", "SSH private key")} hint={t("Хранится на сервере панели. Ключ удалённого сервера запоминается при первом подключении; его замена блокируется.", "Stored on the panel server. The remote host key is remembered on first contact; later changes are rejected.")}><textarea className="input min-h-32 font-mono text-xs" value={form.ssh_key} onChange={change("ssh_key")} autoComplete="off" spellCheck={false} placeholder={t("Вставьте ключ для установки по SSH", "Paste a key for SSH installation")} /></Field>
        </div>
      </details>
      {error && <ErrorState message={error} />}
      <Button type="submit" loading={busy} className="w-full" icon={Plus}>{t("Добавить сервер", "Add server")}</Button>
    </form>
  </Modal>;
}

function RemoteSetup({ node, onClose, onDone }) {
  const { t } = useI18n();
  const existing = node.protocols?.find((protocol) => protocol.name === "shadowsocks");
  const [port, setPort] = useState(8443);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [queued, setQueued] = useState(false);
  async function submit(event) {
    event.preventDefault(); setBusy(true); setError("");
    try { await nodesApi.autoSetup(node.id, { protocol: "shadowsocks", port: Number(port) }); setQueued(true); await onDone(); }
    catch (failure) { setError(apiError(failure)); }
    finally { setBusy(false); }
  }
  return <Modal title={t("Удалённая установка", "Remote installation")} onClose={() => { if (!busy) onClose(); }}>
    <div className="space-y-5">
      <div><p className="font-medium">{node.name}</p><p className="break-all text-sm text-[var(--muted)]">{node.host}</p></div>
      {existing ? <>
        <p className="notice">{t(`Shadowsocks уже сохранён на порту ${existing.port}. Повторная установка может перезаписать конфигурацию сервера. Используйте существующее подключение.`, `Shadowsocks is already saved on port ${existing.port}. Reinstalling can overwrite the remote configuration. Use the existing connection.`)}</p>
        <Link className="btn btn-secondary" to="/protocols">{t("Открыть подключения", "Open connections")}<ArrowUpRight size={16} /></Link>
      </> : queued ? <>
        <div className="notice" role="status">{t("Задача принята. Установка ещё не подтверждена. Обновите список и проверьте появление Shadowsocks; при ошибке проверьте SSH и настройте сервер вручную.", "Task accepted. Installation is not yet confirmed. Refresh the list and check that Shadowsocks appears; if it fails, verify SSH and configure the server manually.")}</div>
        <Button onClick={onClose} className="w-full">{t("Понятно", "Got it")}</Button>
      </> : <form className="space-y-5" onSubmit={submit}>
        <p className="text-sm text-[var(--muted)]">{t("Автоустановка поддерживает Shadowsocks на Debian/Ubuntu с apt и systemd. Она устанавливает пакет и заменяет конфигурацию shadowsocks-libev. Для остальных протоколов нужна ручная установка. Локальный сервер настраивается в разделе подключений.", "Installation supports Shadowsocks on Debian/Ubuntu with apt and systemd. It installs a package and replaces the shadowsocks-libev configuration. Other protocols require manual setup. Configure the local server under Connections.")}</p>
        <Field label={t("Порт Shadowsocks", "Shadowsocks port")} hint={t("Откройте TCP и UDP этого порта на удалённом сервере", "Allow TCP and UDP on this port on the remote server")}><input className="input" type="number" required min={1} max={65535} value={port} onChange={(event) => setPort(event.target.value)} /></Field>
        {error && <ErrorState message={error} />}
        <Button type="submit" icon={Zap} loading={busy} className="w-full">{t("Запустить установку", "Start installation")}</Button>
      </form>}
    </div>
  </Modal>;
}

export default function Nodes() {
  const { t } = useI18n();
  const [nodes, setNodes] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState("");
  const [addOpen, setAddOpen] = useState(false);
  const [setup, setSetup] = useState(null);
  const load = useCallback(async () => {
    setLoading(true); setError("");
    try { const { data } = await nodesApi.list(); setNodes(data); }
    catch (failure) { setError(apiError(failure)); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);
  async function action(key, task) {
    setBusy(key); setNotice("");
    try { await task(); } catch (failure) { toast.error(apiError(failure)); }
    finally { setBusy(""); }
  }
  const check = (node) => action(`check-${node.id}`, async () => {
    const { data } = await nodesApi.check(node.id);
    setNotice(data.status === "online" ? t("Сервер ответил по HTTP. Работу VPN проверьте в клиенте.", "The server responded over HTTP. Verify the VPN in your client.") : t("Нет ответа на HTTP-порту 80. VPN при этом может работать; проверьте подключение в клиенте.", "No response on HTTP port 80. The VPN may still work; check it in your client."));
    await load();
  });
  const remove = (node) => {
    if (!window.confirm(t(`Удалить сервер «${node.name}» и его подключения из панели? Удалённое ПО останется на сервере.`, `Delete “${node.name}” and its connections from the panel? Software on the remote server will remain installed.`))) return;
    action(`delete-${node.id}`, async () => { await nodesApi.delete(node.id); await load(); });
  };
  return <div className="page space-y-6">
    <PageHeader title={t("Серверы", "Servers")} description={t("Адреса серверов и способы подключения к ним", "Your servers and their connection methods")} actions={<>
      <Button variant="secondary" icon={RefreshCw} onClick={load} disabled={loading || !!busy}>{t("Обновить", "Refresh")}</Button>
      <Button icon={Plus} onClick={() => setAddOpen(true)}>{t("Добавить сервер", "Add server")}</Button>
    </>} />
    <p className="notice">{t("Проверка использует HTTP-порт 80 и не проверяет VPN. Конфигурация удалённых серверов применяется вручную; автоустановка доступна только для Shadowsocks.", "Checks use HTTP port 80 and do not test the VPN. Apply remote configurations manually; automatic installation supports Shadowsocks only.")}</p>
    {notice && <div role="status" className="notice">{notice}</div>}
    {loading ? <Loading label={t("Загружаем серверы", "Loading servers")} /> : error ? <ErrorState message={error} onRetry={load} /> : nodes.length === 0 ? <EmptyState icon={Server} title={t("Добавьте первый сервер", "Add your first server")} description={t("Укажите его адрес, затем выберите подключение.", "Enter its address, then choose a connection method.")} action={<Button icon={Plus} onClick={() => setAddOpen(true)}>{t("Добавить сервер", "Add server")}</Button>} /> : <>
      <div className="flex items-center justify-between gap-3"><p className="text-sm text-[var(--muted)]">{t("Всего серверов", "Total servers")}: {nodes.length}</p><Button variant="ghost" icon={RefreshCw} loading={busy === "check-all"} disabled={!!busy} onClick={() => action("check-all", async () => { await nodesApi.checkAll(); setNotice(t("Проверка запущена. Обновите список через несколько секунд.", "Checks started. Refresh the list in a few seconds.")); })}>{t("Проверить все", "Check all")}</Button></div>
      <div className="grid gap-4 xl:grid-cols-2">{nodes.map((node) => <Card key={node.id} className="flex flex-col gap-5">
        <div className="flex items-start justify-between gap-3"><div className="min-w-0"><h2 className="break-words text-base font-semibold">{node.name}</h2><p className="mt-1 break-all text-sm text-[var(--muted)]">{node.host}</p></div><Badge variant={node.status === "online" ? "success" : node.status === "error" ? "danger" : "neutral"}>{node.status === "online" ? t("HTTP доступен", "HTTP reachable") : node.status === "offline" ? t("Нет HTTP-ответа", "No HTTP response") : node.status === "error" ? t("Ошибка настройки", "Setup error") : t("Не проверен", "Not checked")}</Badge></div>
        <div className="flex flex-wrap gap-2">{node.protocols?.length ? node.protocols.map((protocol) => <Badge key={protocol.id} variant={protocol.is_active ? "neutral" : "warning"}>{protocol.name} · {protocol.port}{!protocol.is_active ? t(" · выключено", " · disabled") : ""}</Badge>) : <p className="text-sm text-[var(--muted)]">{t("Подключений пока нет", "No connections yet")}</p>}</div>
        <div className="flex flex-wrap items-center gap-2 border-t border-[var(--border)] pt-4"><Button variant="secondary" icon={RefreshCw} loading={busy === `check-${node.id}`} disabled={!!busy} onClick={() => check(node)}>{t("Проверить", "Check")}</Button><Button variant="ghost" icon={Zap} onClick={() => setSetup(node)} disabled={!!busy}>{t("Установить по SSH", "Install via SSH")}</Button><Button variant="ghost" icon={Trash2} aria-label={t(`Удалить ${node.name}`, `Delete ${node.name}`)} disabled={!!busy} loading={busy === `delete-${node.id}`} onClick={() => remove(node)} /></div>
        <details className="text-sm text-[var(--muted)]"><summary className="cursor-pointer">{t("Технические сведения", "Technical details")}</summary><dl className="mt-3 grid grid-cols-2 gap-2"><dt>SSH</dt><dd className="break-all text-right">{node.ssh_user}:{node.ssh_port}</dd><dt>{t("Группа", "Group")}</dt><dd className="text-right">{node.group || "—"}</dd><dt>{t("Задержка HTTP", "HTTP latency")}</dt><dd className="text-right">{node.latency_ms == null ? "—" : `${Math.round(node.latency_ms)} ms`}</dd></dl></details>
      </Card>)}</div>
    </>}
    {addOpen && <AddNode onClose={() => setAddOpen(false)} onCreated={load} />}
    {setup && <RemoteSetup node={setup} onClose={() => setSetup(null)} onDone={load} />}
  </div>;
}
