import React, { useState } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { ArrowUpRight, LayoutDashboard, LogOut, Menu, Moon, Server, Settings, ShieldCheck, Sun, Users, X } from "lucide-react";
import { useAuthStore, useI18n, usePreferences } from "../store";
import { Button } from "./ui";

export function PreferencesControls() {
  const { language, t } = useI18n();
  const { theme, setTheme, setLanguage } = usePreferences();
  const dark = theme === "dark" || (theme === "system" && window.matchMedia("(prefers-color-scheme: dark)").matches);
  return <div className="flex gap-2"><Button variant="ghost" onClick={() => setLanguage(language === "ru" ? "en" : "ru")} aria-label={`${language.toUpperCase()} · ${t("Switch to English", "Переключить на русский")}`}>{language.toUpperCase()}</Button><Button variant="ghost" className="!px-3" icon={dark ? Sun : Moon} onClick={() => setTheme(dark ? "light" : "dark")} aria-label={t("Переключить тему", "Toggle theme")} /></div>;
}

export default function Layout() {
  const [open, setOpen] = useState(false);
  const { t } = useI18n();
  const user = useAuthStore((s) => s.user);
  const logout = useAuthStore((s) => s.logout);
  const navigate = useNavigate();
  const links = [["/dashboard", LayoutDashboard, t("Обзор", "Overview")], ["/nodes", Server, t("Серверы", "Servers")], ["/users", Users, t("Пользователи", "Users")], ["/protocols", ShieldCheck, t("Подключения", "Connections")], ["/settings", Settings, t("Настройки", "Settings")]];
  const navigation = <>{links.map(([path, Icon, label]) => <NavLink to={path} key={path} className={({ isActive }) => `nav-link ${isActive ? "active" : ""}`} onClick={() => setOpen(false)}><Icon size={20} aria-hidden="true" />{label}</NavLink>)}</>;
  return <div className="min-h-dvh lg:pl-64">
    <a href="#main" className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-50 btn btn-primary">{t("К содержимому", "Skip to content")}</a>
    <aside className="fixed inset-y-0 left-0 hidden w-64 flex-col border-r border-line bg-surface p-5 lg:flex"><NavLink to="/dashboard" className="flex min-h-11 items-center gap-3 px-2"><div className="icon-box"><ShieldCheck size={24} /></div><span className="text-xl font-semibold tracking-tight">FVpn<span className="muted ml-2 text-xs font-normal">panel</span></span></NavLink><div className="my-7 border-t border-line" /><nav aria-label={t("Основная навигация", "Main navigation")} className="space-y-2">{navigation}</nav><div className="mt-auto space-y-4 pt-6"><div className="notice"><p className="text-xs font-semibold">{t("Ваш сервер. Ваше подключение.", "Your server. Your connection.")}</p><a href="https://github.com/franklin-lol/FVpn" target="_blank" rel="noreferrer" className="mt-3 inline-flex min-h-11 items-center gap-2 text-xs text-accent">GitHub <ArrowUpRight size={14} /></a></div><Button variant="ghost" icon={LogOut} className="w-full justify-start" onClick={() => { logout(); navigate("/login"); }}>{t("Выйти", "Sign out")} · {user}</Button></div></aside>
    <header className="sticky top-0 z-20 flex min-h-20 items-center justify-between gap-4 border-b border-line bg-surface px-4 sm:px-8"><div className="flex items-center gap-3"><Button variant="ghost" icon={open ? X : Menu} className="!px-3 lg:hidden" aria-label={t("Меню", "Menu")} aria-expanded={open} aria-controls="mobile-navigation" onClick={() => setOpen(!open)} /><span className="font-semibold lg:hidden">FVpn</span><span className="muted hidden text-sm lg:block">{t("Личное пространство подключения", "Your connection workspace")}</span></div><PreferencesControls /></header>
    {open && <nav id="mobile-navigation" aria-label={t("Навигация", "Navigation")} className="sticky top-20 z-20 space-y-1 border-b border-line bg-surface p-4 lg:hidden">{navigation}<Button variant="ghost" icon={LogOut} className="w-full justify-start" onClick={() => { logout(); navigate("/login"); }}>{t("Выйти", "Sign out")}</Button></nav>}
    <main id="main" tabIndex={-1}><Outlet /></main>
  </div>;
}
