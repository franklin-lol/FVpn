import React, { useCallback, useEffect, useState } from "react";
import { Check, Code2, Pencil, Plus, RefreshCw, Shield, Trash2 } from "lucide-react";
import { Link } from "react-router-dom";
import toast from "react-hot-toast";
import { apiError, nodesApi, protocolsApi } from "../utils/api";
import { useI18n } from "../store";
import { Badge, Button, Card, CopyButton, EmptyState, ErrorState, Field, Loading, Modal, PageHeader } from "../components/ui";

const MANAGED = ["vless", "shadowsocks", "hysteria2", "trojan", "tuic", "shadowtls", "vmess"];
const TITLES = { vless: "VLESS Reality", shadowsocks: "Shadowsocks", hysteria2: "Hysteria2", trojan: "Trojan", tuic: "TUIC", shadowtls: "ShadowTLS", vmess: "VMess" };
const PORTS = { vless: 443, shadowsocks: 8443, hysteria2: 8444, trojan: 8445, tuic: 8446, shadowtls: 8447, vmess: 8448 };
function readOptions(text, t) {
  let parsed;
  try { parsed = JSON.parse(text); } catch { throw new Error(t("Некорректный JSON. Проверьте кавычки и запятые.", "Invalid JSON. Check quotes and commas.")); }
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) throw new Error(t("Параметры должны быть JSON-объектом.", "Options must be a JSON object."));
  return parsed;
}

function ProtocolEditor({ protocol, nodes, supported, onClose, onSaved }) {
  const { t } = useI18n();
  const editing = !!protocol;
  const [form, setForm] = useState({ node_id: protocol?.node_id || nodes[0]?.id || "", name: protocol?.name || "vless", port: protocol?.port || 443, is_active: protocol?.is_active ?? true });
  const [advanced, setAdvanced] = useState(false);
  const [options, setOptions] = useState(editing ? JSON.stringify(protocol.config || {}, null, 2) : "{}");
  const [optionsChanged, setOptionsChanged] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const change = (key) => (event) => setForm((previous) => ({ ...previous, [key]: event.target.value }));
  async function submit(event) {
    event.preventDefault(); setError(""); setBusy(true);
    try {
      const payload = { port: Number(form.port), ...(optionsChanged || !editing ? { config: readOptions(options, t) } : {}) };
      let result;
      if (editing) result = await protocolsApi.update(protocol.id, { ...payload, is_active: form.is_active });
      else result = await protocolsApi.create({ ...payload, node_id: Number(form.node_id), name: form.name });
      await onSaved(result.data.node_id); onClose();
    } catch (failure) { setError(failure.response ? apiError(failure) : failure.message); }
    finally { setBusy(false); }
  }
  return <Modal title={editing ? t("Изменить подключение", "Edit connection") : t("Добавить подключение", "Add a connection")} onClose={() => { if (!busy) onClose(); }}>
    <form className="space-y-5" onSubmit={submit}>
      {!editing && <>
        <p className="text-sm text-[var(--muted)]">{t("Для начала выберите VLESS Reality: ключи будут созданы автоматически. Для TLS-протоколов нужен сертификат, которому доверяет клиент.", "Start with VLESS Reality: keys are generated automatically. TLS protocols require a certificate trusted by the client.")}</p>
        <Field label={t("Сервер", "Server")}><select className="input" required value={form.node_id} onChange={change("node_id")}><option value="">{t("Выберите сервер", "Choose a server")}</option>{nodes.map((node) => <option key={node.id} value={node.id}>{node.name} · {node.host}</option>)}</select></Field>
        <Field label={t("Способ подключения", "Connection method")}><select className="input" value={form.name} onChange={(event) => setForm((previous) => ({ ...previous, name: event.target.value, port: PORTS[event.target.value] || 443 }))}>{supported.map((item) => <option key={item.name} value={item.name}>{TITLES[item.name] || item.name}{item.name === "vless" ? t(" · рекомендуется", " · recommended") : ""}</option>)}</select></Field>
      </>}
      {editing && <p className="text-sm text-[var(--muted)]">{TITLES[protocol.name] || protocol.name} · {nodes.find((node) => node.id === protocol.node_id)?.name || `#${protocol.node_id}`}</p>}
      <Field label={t("Порт подключения", "Connection port")} hint={t("Порт должен быть свободен и открыт в межсетевом экране", "The port must be available and allowed through the firewall")}><input className="input" type="number" required min={1} max={65535} value={form.port} onChange={change("port")} /></Field>
      {editing && <label className="flex min-h-11 items-center gap-3 text-sm"><input type="checkbox" className="h-5 w-5 accent-[var(--accent)]" checked={form.is_active} onChange={(event) => setForm((previous) => ({ ...previous, is_active: event.target.checked }))} />{t("Включено в конфигурацию сервера", "Enabled in the server configuration")}</label>}
      <details className="rounded-xl border border-[var(--border)] p-4" onToggle={(event) => setAdvanced(event.currentTarget.open)}>
        <summary className="cursor-pointer text-sm font-medium">{t("Дополнительно: показать и изменить параметры", "Advanced: reveal and edit options")}</summary>
        {advanced && <div className="mt-4 space-y-3"><p className="text-sm text-[var(--muted)]">{t("Здесь есть секреты подключения. Объект заменяет параметры целиком; сохраните нужные ключи. Названия и типы проверяет сервер.", "These options include connection secrets. This object replaces all options; preserve required keys. The server validates names and types.")}</p><Field label={t("Параметры протокола (JSON)", "Protocol options (JSON)")} hint={t("Например: sni, flow, method, tls_insecure. Допустимые поля — в API-документации.", "Examples: sni, flow, method, tls_insecure. See the API documentation for allowed fields.")}><textarea className="input min-h-56 font-mono text-xs" value={options} onChange={(event) => { setOptions(event.target.value); setOptionsChanged(true); }} autoComplete="off" spellCheck={false} /></Field><a className="text-sm text-[var(--accent)] underline" href="/api/docs" target="_blank" rel="noopener noreferrer">{t("Открыть API-документацию", "Open API documentation")}</a></div>}
      </details>
      {error && <ErrorState message={error} />}
      <Button type="submit" icon={Check} loading={busy} className="w-full">{editing ? t("Сохранить изменения", "Save changes") : t("Добавить подключение", "Add connection")}</Button>
      <p className="text-xs text-[var(--muted)]">{t("Сохранение записывает параметры в базу. Результат применения проверьте отдельной кнопкой на карточке.", "Saving writes options to the database. Verify application with the separate button on the card.")}</p>
    </form>
  </Modal>;
}

export default function Protocols() {
  const { t } = useI18n();
  const [protocols, setProtocols] = useState([]);
  const [nodes, setNodes] = useState([]);
  const [supported, setSupported] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [editor, setEditor] = useState(null);
  const [busy, setBusy] = useState("");
  const [results, setResults] = useState({});
  const [notice, setNotice] = useState("");
  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const [connections, servers, catalogue] = await Promise.all([protocolsApi.list(), nodesApi.list(), protocolsApi.supported()]);
      setProtocols(connections.data); setNodes(servers.data);
      setSupported((catalogue.data.protocols || []).filter((item) => MANAGED.includes(item.name)).sort((a, b) => MANAGED.indexOf(a.name) - MANAGED.indexOf(b.name)));
    } catch (failure) { setError(apiError(failure)); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);
  async function saved(nodeId) {
    setResults((previous) => ({ ...previous, [nodeId]: { state: "queued", message: t("Сохранено. Применение ещё не подтверждено; нажмите «Применить и проверить».", "Saved. Application is not yet confirmed; select Apply and verify.") } }));
    await load();
  }
  async function sync(nodeId) {
    setBusy(`sync-${nodeId}`);
    try {
      const { data } = await protocolsApi.sync(nodeId);
      const failureMessages = {
        manual_required: t("Удалённый сервер требует ручного применения конфигурации.", "Apply the remote server configuration manually."),
        validation_failed: t("Конфигурация не прошла проверку. Исправьте параметры и повторите применение.", "Configuration validation failed. Correct the options and apply again."),
        rolled_back: t("Применение не удалось. Восстановлена предыдущая конфигурация.", "Application failed. The previous configuration was restored."),
        rollback_failed: t("Ошибка применения и восстановления. Проверьте службы на сервере.", "Application and recovery failed. Check services on the server."),
        unsupported_protocol: t("Включён неподдерживаемый протокол. Отключите его и повторите.", "An unsupported protocol is enabled. Disable it and retry."),
      };
      const state = data.status === "applied" ? "applied" : failureMessages[data.status] ? "error" : "queued";
      setResults((previous) => ({ ...previous, [nodeId]: { state, message: failureMessages[data.status] || (state === "applied" ? t("Конфигурация проверена и применена.", "Configuration validated and applied.") : t("Задача применения принята. Сервер пока не подтвердил результат.", "Application task accepted. The server has not confirmed the result yet.")) } }));
    } catch (failure) { setResults((previous) => ({ ...previous, [nodeId]: { state: "error", message: apiError(failure) } })); }
    finally { setBusy(""); }
  }
  async function remove(protocol) {
    if (!window.confirm(t(`Удалить ${TITLES[protocol.name] || protocol.name} на порту ${protocol.port}? Клиенты этого подключения потеряют доступ после применения.`, `Delete ${TITLES[protocol.name] || protocol.name} on port ${protocol.port}? Its clients lose access after application.`))) return;
    setBusy(`delete-${protocol.id}`);
    try { await protocolsApi.delete(protocol.id); await saved(protocol.node_id); setNotice(t("Подключение удалено из базы. Примените оставшуюся конфигурацию сервера.", "Connection removed from the database. Apply the remaining server configuration.")); }
    catch (failure) { toast.error(apiError(failure)); }
    finally { setBusy(""); }
  }
  return <div className="page space-y-6">
    <PageHeader title={t("Подключения", "Connections")} description={t("Способы доступа к вашим серверам", "Connection methods for your servers")} actions={<><Button variant="secondary" icon={RefreshCw} onClick={load} disabled={loading || !!busy}>{t("Обновить", "Refresh")}</Button><Button icon={Plus} onClick={() => setEditor({})} disabled={!nodes.length || !supported.length}>{t("Добавить подключение", "Add connection")}</Button></>} />
    <p className="notice">{t("VLESS Reality — рекомендуемый вариант для старта. Учётные данные протоколов общие для подписок; персональные квоты не применяются. Удалённые серверы настраиваются вручную. WireGuard не экспортируется.", "VLESS Reality is recommended to get started. Protocol credentials are shared by subscriptions; individual quotas are not enforced. Configure remote servers manually. WireGuard is excluded from exports.")}</p>
    {notice && <p className="notice" role="status">{notice}</p>}
    {loading ? <Loading label={t("Загружаем подключения", "Loading connections")} /> : error ? <ErrorState message={error} onRetry={load} /> : !nodes.length ? <EmptyState icon={Shield} title={t("Сначала добавьте сервер", "Add a server first")} description={t("Подключение всегда относится к конкретному серверу.", "Each connection belongs to a server.")} action={<Link className="btn btn-primary" to="/nodes">{t("Открыть серверы", "Open servers")}</Link>} /> : <>
      {protocols.length === 0 && <EmptyState icon={Shield} title={t("Создайте первое подключение", "Create your first connection")} description={t("Выберите сервер и рекомендуемый VLESS Reality.", "Choose a server and the recommended VLESS Reality preset.")} action={<Button icon={Plus} onClick={() => setEditor({})} disabled={!supported.length}>{t("Добавить подключение", "Add connection")}</Button>} />}
      {nodes.map((node) => {
        const items = protocols.filter((protocol) => protocol.node_id === node.id);
        if (!items.length && !results[node.id]) return null;
        const result = results[node.id];
        return <section key={node.id} className="space-y-3" aria-label={node.name}>
          <div className="flex flex-wrap items-center justify-between gap-3"><div><h2 className="text-base font-semibold">{node.name}</h2><p className="break-all text-sm text-[var(--muted)]">{node.host}</p></div><Button variant="secondary" icon={RefreshCw} disabled={!!busy} loading={busy === `sync-${node.id}`} onClick={() => sync(node.id)}>{t("Применить и проверить", "Apply and verify")}</Button></div>
          {result && <p role="status" className={`notice ${result.state === "error" ? "text-[var(--danger)]" : result.state === "applied" ? "text-[var(--success)]" : ""}`}>{result.message}</p>}
          <div className="grid gap-4 xl:grid-cols-2">{items.map((protocol) => <Card key={protocol.id} className="space-y-4">
            <div className="flex items-start justify-between gap-3"><div><h3 className="font-semibold">{TITLES[protocol.name] || protocol.name}</h3><p className="mt-1 text-sm text-[var(--muted)]">{t("Порт", "Port")} {protocol.port}</p></div><Badge variant={protocol.is_active ? "success" : "neutral"}>{protocol.is_active ? t("Включено в базе", "Enabled in database") : t("Выключено", "Disabled")}</Badge></div>
            {!MANAGED.includes(protocol.name) && <p className="text-sm text-[var(--warn)]">{t("Существующая запись сохранена. Этот протокол не поддерживается как управляемый пресет.", "Existing record preserved. This protocol is not supported as a managed preset.")}</p>}
            <div className="flex flex-wrap gap-2"><Button variant="secondary" icon={Pencil} disabled={!!busy} onClick={() => setEditor({ protocol })}>{t("Изменить", "Edit")}</Button><Button variant="ghost" icon={Trash2} disabled={!!busy} loading={busy === `delete-${protocol.id}`} onClick={() => remove(protocol)}>{t("Удалить", "Delete")}</Button></div>
            <details className="border-t border-[var(--border)] pt-4"><summary className="cursor-pointer text-sm text-[var(--muted)]">{t("Показать конфигурацию и секреты", "Reveal configuration and secrets")}</summary><SecretConfig value={protocol.config} /></details>
          </Card>)}</div>
        </section>;
      })}
    </>}
    {editor && <ProtocolEditor protocol={editor.protocol} nodes={nodes} supported={supported} onClose={() => setEditor(null)} onSaved={saved} />}
  </div>;
}

function SecretConfig({ value }) {
  const { t } = useI18n();
  const [revealed, setRevealed] = useState(false);
  return <div className="mt-4 space-y-3">{revealed ? <><div className="flex justify-end"><CopyButton text={JSON.stringify(value || {}, null, 2)} /></div><pre className="max-h-64 overflow-auto rounded-xl bg-[var(--surface-soft)] p-4 font-mono text-xs">{JSON.stringify(value || {}, null, 2)}</pre></> : <Button variant="secondary" icon={Code2} onClick={() => setRevealed(true)}>{t("Показать секреты", "Reveal secrets")}</Button>}</div>;
}
