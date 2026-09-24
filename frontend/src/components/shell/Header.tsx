import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { Bell, ChevronDown, Menu, Search, ShieldCheck } from "lucide-react";
import type { UserRead } from "../../types/auth";
import type { Lang } from "../../i18n/LangContext";
import { copy } from "../../i18n/copy";
import { useLang } from "../../i18n/useLang";
import { GearIcon } from "../icons/SettingsIcons";
import { SettingsModal } from "../settings/SettingsModal";
import { useNotifications } from "../common/NotificationContext";
import { NotificationList } from "../common/NotificationList";

function getInitials(user: UserRead): string {
  if (user.full_name) {
    const parts = user.full_name.trim().split(/\s+/);
    return ((parts[0]?.[0] ?? "") + (parts[1]?.[0] ?? "")).toUpperCase();
  }
  return user.email[0]?.toUpperCase() ?? "?";
}

const LANG_OPTIONS: { value: Lang; label: string }[] = [
  { value: "fr", label: "Français" },
  { value: "en", label: "English" },
];

interface HeaderProps {
  user: UserRead;
  // Only the Workspace page currently has anything to search — omit these to render the header
  // without a (non-functional) search box rather than showing one that does nothing everywhere.
  searchQuery?: string;
  onSearchChange?: (value: string) => void;
  // Opens the sidebar drawer (see AppShell.tsx/css) — the sidebar is never permanently visible
  // at any width, so this is the only way to reach Word Files/Admin nav.
  onMenuClick: () => void;
}

export function Header({ user, searchQuery, onSearchChange, onMenuClick }: HeaderProps) {
  const { lang, setLang } = useLang();
  const t = copy[lang];
  const { notifications, unreadCount, markAllRead } = useNotifications();
  const [menuOpen, setMenuOpen] = useState(false);
  const [langMenuOpen, setLangMenuOpen] = useState(false);
  const [notifMenuOpen, setNotifMenuOpen] = useState(false);
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
  const langMenuRef = useRef<HTMLDivElement>(null);
  const notifMenuRef = useRef<HTMLDivElement>(null);
  const activeLang = LANG_OPTIONS.find((option) => option.value === lang) ?? LANG_OPTIONS[0];

  useEffect(() => {
    if (!menuOpen && !langMenuOpen && !notifMenuOpen) return;
    function handleClick(event: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        setMenuOpen(false);
      }
      if (langMenuRef.current && !langMenuRef.current.contains(event.target as Node)) {
        setLangMenuOpen(false);
      }
      if (notifMenuRef.current && !notifMenuRef.current.contains(event.target as Node)) {
        setNotifMenuOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [menuOpen, langMenuOpen, notifMenuOpen]);

  return (
    <header className="shell-header">
      <div className="shell-header-start">
        <button
          type="button"
          className="shell-hamburger"
          onClick={onMenuClick}
          aria-label="Open menu"
        >
          <Menu size={20} />
        </button>

        <div className="shell-header-brand">
          <img src="/antic_logo.png" alt="ANTIC" />
          <span>SheetFlow</span>
        </div>
      </div>

      <div className="shell-search">
        {onSearchChange && (
          <>
            <Search size={16} />
            <input
              type="search"
              placeholder={t.searchPlaceholder}
              aria-label={t.searchPlaceholder}
              value={searchQuery ?? ""}
              onChange={(event) => onSearchChange(event.target.value)}
            />
          </>
        )}
      </div>

      <div className="shell-header-right">
        <div className="shell-notification-picker" ref={notifMenuRef}>
          <button
            type="button"
            className="shell-notification-trigger"
            onClick={() => {
              const opening = !notifMenuOpen;
              setNotifMenuOpen(opening);
              // Viewing the dropdown is what "acknowledges" a notification — the badge's job is
              // to say "something happened since you last looked," not to nag after you've
              // actually looked.
              if (opening && unreadCount > 0) markAllRead();
            }}
            aria-label={t.navNotifications}
            title={t.navNotifications}
          >
            <Bell size={17} />
            {unreadCount > 0 && <span className="shell-notification-badge" />}
          </button>

          {notifMenuOpen && (
            <div className="shell-notification-menu">
              <div className="shell-notification-menu-header">
                <span>{t.navNotifications}</span>
              </div>
              <NotificationList notifications={notifications} emptyMessage={t.notificationsEmpty} limit={6} />
              <Link
                to="/notifications"
                className="shell-notification-menu-footer"
                onClick={() => setNotifMenuOpen(false)}
              >
                {t.viewAllNotificationsLabel}
              </Link>
            </div>
          )}
        </div>

        <div className="shell-lang-picker" ref={langMenuRef}>
          <button
            type="button"
            className="shell-lang-trigger"
            onClick={() => setLangMenuOpen((open) => !open)}
            aria-label="Language"
          >
            <span>{activeLang.value.toUpperCase()}</span>
            <ChevronDown size={13} />
          </button>

          {langMenuOpen && (
            <div className="shell-lang-menu">
              {LANG_OPTIONS.map(({ value, label }) => (
                <button
                  key={value}
                  type="button"
                  className={`shell-lang-menu-item ${lang === value ? "active" : ""}`}
                  onClick={() => {
                    setLang(value);
                    setLangMenuOpen(false);
                  }}
                >
                  {label}
                </button>
              ))}
            </div>
          )}
        </div>

        <div className="shell-account" ref={menuRef}>
          <button
            type="button"
            className="shell-account-pill"
            onClick={() => setMenuOpen((open) => !open)}
          >
            <span className="shell-avatar">{getInitials(user)}</span>
            <span className="shell-account-text">
              <span className="shell-account-name">{user.full_name ?? user.email}</span>
              <span className="shell-account-role">
                <ShieldCheck size={11} /> {t.anticWorker}
              </span>
            </span>
          </button>

          {menuOpen && (
            <div className="shell-account-menu">
              <div className="shell-account-menu-header">
                <span className="shell-avatar shell-avatar-lg">{getInitials(user)}</span>
                <div>
                  <div className="shell-account-menu-name">{user.full_name ?? user.email}</div>
                  <div className="shell-account-menu-email">{user.email}</div>
                </div>
              </div>
              <button
                type="button"
                className="shell-account-menu-item"
                onClick={() => {
                  setMenuOpen(false);
                  setIsSettingsOpen(true);
                }}
              >
                <GearIcon /> {t.settings}
              </button>
            </div>
          )}
        </div>
      </div>

      {isSettingsOpen && <SettingsModal onClose={() => setIsSettingsOpen(false)} />}
    </header>
  );
}
