import { useEffect, useRef, useState } from "react";
import { Menu, Search, ShieldCheck } from "lucide-react";
import type { UserRead } from "../../types/auth";
import { copy } from "../../i18n/copy";
import { useLang } from "../../i18n/useLang";
import { GearIcon } from "../icons/SettingsIcons";
import { SettingsModal } from "../settings/SettingsModal";

function getInitials(user: UserRead): string {
  if (user.full_name) {
    const parts = user.full_name.trim().split(/\s+/);
    return ((parts[0]?.[0] ?? "") + (parts[1]?.[0] ?? "")).toUpperCase();
  }
  return user.email[0]?.toUpperCase() ?? "?";
}

interface HeaderProps {
  user: UserRead;
  // Only the Workspace page currently has anything to search — omit these to render the header
  // without a (non-functional) search box rather than showing one that does nothing everywhere.
  searchQuery?: string;
  onSearchChange?: (value: string) => void;
  // Opens the mobile off-canvas sidebar drawer (see AppShell.tsx/css) — only rendered visible
  // below the mobile breakpoint via CSS, since on desktop the sidebar is already always visible.
  onMenuClick: () => void;
}

export function Header({ user, searchQuery, onSearchChange, onMenuClick }: HeaderProps) {
  const { lang, setLang } = useLang();
  const t = copy[lang];
  const [menuOpen, setMenuOpen] = useState(false);
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!menuOpen) return;
    function handleClick(event: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        setMenuOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [menuOpen]);

  return (
    <header className="shell-header">
      <button
        type="button"
        className="shell-hamburger"
        onClick={onMenuClick}
        aria-label="Open menu"
      >
        <Menu size={20} />
      </button>

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
        <div className="shell-lang-toggle">
          <button type="button" className={lang === "fr" ? "active" : ""} onClick={() => setLang("fr")}>
            FR
          </button>
          <button type="button" className={lang === "en" ? "active" : ""} onClick={() => setLang("en")}>
            EN
          </button>
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
                <div className="shell-account-menu-name">{user.full_name ?? user.email}</div>
                <div className="shell-account-menu-email">{user.email}</div>
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
