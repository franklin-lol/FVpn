import React, { useEffect, useId, useRef, useState } from "react";
import { AlertCircle, Check, Copy, Loader2, RefreshCw, X } from "lucide-react";
import { useI18n } from "../store";

export function Button({ children, variant = "primary", loading = false, icon: Icon, className = "", disabled, type = "button", ...props }) {
  return <button type={type} className={`btn btn-${variant} ${className}`} disabled={disabled || loading} aria-busy={loading || undefined} {...props}>
    {loading ? <Loader2 size={18} className="animate-spin" aria-hidden="true" /> : Icon ? (React.isValidElement(Icon) ? Icon : <Icon size={18} aria-hidden="true" />) : null}{children}
  </button>;
}
export function Card({ children, className = "", title, ...props }) {
  return <section className={`card ${className}`} {...props}>{title && <h2 className="mb-4">{title}</h2>}{children}</section>;
}
export function PageHeader({ title, description, actions }) {
  return <header className="flex flex-wrap items-start justify-between gap-4"><div className="space-y-2"><h1>{title}</h1>{description && <p className="muted max-w-2xl text-sm">{description}</p>}</div>{actions && <div className="flex flex-wrap gap-2">{actions}</div>}</header>;
}
export function Field({ label, hint, children, className = "" }) {
  const generated = useId();
  const child = React.Children.only(children);
  const nestedControl = !["input", "select", "textarea"].includes(child.type) && React.Children.toArray(child.props.children).find((element) => React.isValidElement(element) && ["input", "select", "textarea"].includes(element.type));
  const id = (nestedControl ? nestedControl.props.id : child.props.id) || generated;
  const control = nestedControl || child;
  const attributes = { id, "aria-describedby": hint ? `${id}-hint` : control.props["aria-describedby"] };
  const rendered = nestedControl
    ? React.cloneElement(child, {}, React.Children.map(child.props.children, (element) => element === nestedControl ? React.cloneElement(element, attributes) : element))
    : React.cloneElement(child, attributes);
  return <div className={`space-y-2 ${className}`}><label className="block text-sm font-semibold" htmlFor={id}>{label}</label>{rendered}{hint && <p id={`${id}-hint`} className="muted text-xs leading-relaxed">{hint}</p>}</div>;
}
export function Badge({ children, variant = "neutral", className = "" }) {
  return <span className={`badge badge-${variant} ${className}`}>{children}</span>;
}
export function Modal({ title, onClose, children, wide = false }) {
  const ref = useRef(null);
  const heading = useId();
  const { t } = useI18n();
  useEffect(() => { const dialog = ref.current; dialog.showModal(); return () => dialog.close(); }, []);
  return <dialog ref={ref} className={`dialog ${wide ? "!max-w-3xl" : ""}`} aria-labelledby={heading} onCancel={(event) => { event.preventDefault(); onClose(); }} onClick={(event) => { if (event.target === ref.current) { const rect = ref.current.getBoundingClientRect(); if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) onClose(); } }}>
    <div className="flex items-center justify-between gap-4 border-b border-line px-5 py-4"><h2 id={heading}>{title}</h2><Button variant="ghost" aria-label={t("Закрыть", "Close")} onClick={onClose} icon={X} className="!px-3" /></div><div className="space-y-5 p-5 sm:p-6">{children}</div>
  </dialog>;
}
export function Loading({ label }) {
  const { t } = useI18n();
  return <div role="status" aria-label={label || t("Загрузка", "Loading")} className="space-y-4"><span className="sr-only">{label || t("Загрузка", "Loading")}</span>{[1, 2, 3].map((n) => <div className="card space-y-3" key={n}><div className="skeleton w-1/3" /><div className="skeleton w-2/3" /></div>)}</div>;
}
export function ErrorState({ message, error, onRetry }) {
  const { t } = useI18n();
  const detail = message || error;
  const localized = {
    "Current password is incorrect": t("Текущий пароль неверен. Проверьте его и повторите.", "Current password is incorrect. Check it and try again."),
    "New password must differ from the current password": t("Новый пароль должен отличаться от текущего.", "New password must differ from the current password."),
    "Network Error": t("Сервер недоступен. Проверьте соединение и повторите.", "Server unavailable. Check your connection and try again."),
    "Username already exists": t("Это имя уже занято. Выберите другое.", "This username is taken. Choose another."),
  };
  return <div role="alert" className="notice notice-danger flex flex-wrap items-center gap-3"><AlertCircle size={20} aria-hidden="true" /><div className="min-w-0 flex-1"><p className="font-semibold">{t("Не удалось выполнить запрос", "Request failed")}</p><p className="break-words">{localized[detail] || detail || t("Проверьте соединение и повторите.", "Check your connection and try again.")}</p></div>{onRetry && <Button variant="secondary" icon={RefreshCw} onClick={onRetry}>{t("Повторить", "Retry")}</Button>}</div>;
}
export function EmptyState({ title, description, action, icon: Icon }) {
  return <Card className="flex flex-col items-center gap-4 py-10 text-center">{Icon && <div className="icon-box"><Icon size={22} aria-hidden="true" /></div>}<h2>{title}</h2>{description && <p className="muted max-w-md text-sm">{description}</p>}{action}</Card>;
}
export function CopyButton({ text, children, className = "", ...props }) {
  const [state, setState] = useState("idle");
  const { t } = useI18n();
  useEffect(() => { setState("idle"); }, [text]);
  const copy = async () => {
    try { await navigator.clipboard.writeText(text); setState("done"); }
    catch { setState("error"); }
  };
  return <div className={className}><Button variant="secondary" icon={state === "done" ? Check : Copy} onClick={copy} {...props}>{state === "done" ? t("Скопировано", "Copied") : children || t("Копировать", "Copy")}</Button>{state === "error" && <p className="muted mt-2 text-xs" role="status">{t("Не удалось скопировать. Выделите ссылку вручную.", "Could not copy. Select the link manually.")}</p>}</div>;
}
