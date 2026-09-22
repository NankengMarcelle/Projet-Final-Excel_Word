import { useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { Bell, ChevronLeft, ChevronRight, FileText, FolderOpen, LogOut, ShieldCheck, Star, X } from "lucide-react";
import type { UserRead } from "../../types/auth";
import { copy } from "../../i18n/copy";
import { useLang } from "../../i18n/useLang";

interface SidebarProps {
  user: UserRead;
  onLogout: () => void;
  // Mobile-only off-canvas drawer state, owned by AppShell (not this component) since the
  // header's hamburger button — a sibling, not a descendant — also needs to open it. Has no
  // visual effect above the mobile breakpoint; see AppShell.css.
  isMobileOpen: boolean;
  onMobileClose: () => void;
}

const COLLAPSED_KEY = "sheetflow_sidebar_collapsed";

export function Sidebar({ user, onLogout, isMobileOpen, onMobileClose }: SidebarProps) {
  const { lang } = useLang();
  const t = copy[lang];
  const location = useLocation();
  // The editor route (/workbooks/:id) never renders this Sidebar at all (see AppShell.tsx), so
  // the only paths this ever actually needs to match against are /workspace and /word-files.
  const isWorkbooks = location.pathname === "/workspace";
  const isWordFiles = location.pathname === "/word-files";

  // Self-contained (not lifted to AppShell): the sidebar owns its own collapsed state and
  // persistence, same "isolated" collapsible-chrome idea already used for the editor's title
  // bar/toolbar (see EditorPage.tsx's CHROME_COLLAPSED_KEY) — nothing outside this component
  // needs to know or care whether it's collapsed.
  const [collapsed, setCollapsed] = useState(() => localStorage.getItem(COLLAPSED_KEY) === "1");

  function toggleCollapsed() {
    setCollapsed((current) => {
      const next = !current;
      localStorage.setItem(COLLAPSED_KEY, next ? "1" : "0");
      return next;
    });
  }

  return (
    <aside className={`shell-sidebar ${collapsed ? "collapsed" : ""} ${isMobileOpen ? "mobile-open" : ""}`}>
      <div>
        <div className="shell-sidebar-brand">
          {/* Mobile drawer only (hidden via CSS above the mobile breakpoint) — the backdrop and
              tapping a nav link both close the drawer too, this is just the explicit affordance. */}
          <button
            type="button"
            className="shell-sidebar-close"
            onClick={onMobileClose}
            aria-label="Close menu"
          >
            <X size={18} />
          </button>
          <div className="shell-sidebar-logo">
            <img src="/antic_logo.png" alt="ANTIC" />
          </div>
          <span className="shell-sidebar-name">ANTIC</span>
          <span className="shell-sidebar-tagline">(Agence Nationale des Technologies de l'Information et de la Communication)</span>
        </div>

        {/* Cameroon flag tricolor ribbon — ANTIC is Cameroon's national ICT agency */}
        <div className="shell-flag-ribbon">
          <div className="shell-flag-band shell-flag-green" />
          <div className="shell-flag-band shell-flag-red">
            <Star size={8} color="#FCD116" fill="#FCD116" />
          </div>
          <div className="shell-flag-band shell-flag-yellow" />
        </div>

        <nav className="shell-nav">
          <Link
            to="/workspace"
            className={`shell-nav-item ${isWorkbooks ? "active" : ""}`}
            title={t.navWorkbooks}
            onClick={onMobileClose}
          >
            <FolderOpen size={16} />
            <span>{t.navWorkbooks}</span>
          </Link>

          <Link
            to="/word-files"
            className={`shell-nav-item ${isWordFiles ? "active" : ""}`}
            title={t.navWordFiles}
            onClick={onMobileClose}
          >
            <FileText size={16} />
            <span>{t.navWordFiles}</span>
          </Link>

          <button type="button" className="shell-nav-item disabled" disabled title={t.comingSoon}>
            <Bell size={16} />
            <span>{t.navNotifications}</span>
          </button>

          {user.role === "admin" && (
            <Link
              to="/admin"
              className={`shell-nav-item ${location.pathname === "/admin" ? "active" : ""}`}
              title={t.navAdmin}
              onClick={onMobileClose}
            >
              <ShieldCheck size={16} />
              <span>{t.navAdmin}</span>
            </Link>
          )}
        </nav>
      </div>

      <div className="shell-sidebar-footer">
        <button
          type="button"
          className="shell-nav-item shell-collapse-btn"
          onClick={toggleCollapsed}
          title={collapsed ? t.expandSidebar : t.collapseSidebar}
        >
          {collapsed ? <ChevronRight size={16} /> : <ChevronLeft size={16} />}
          <span>{collapsed ? t.expandSidebar : t.collapseSidebar}</span>
        </button>
        <button type="button" className="shell-logout-btn" onClick={onLogout} title={t.logOut}>
          <LogOut size={14} />
          <span>{t.logOut}</span>
        </button>
      </div>
    </aside>
  );
}
