import { useState } from "react";
import { Outlet, useLocation } from "react-router-dom";
import { useAuth } from "../../auth/useAuth";
import { Sidebar } from "./Sidebar";
import { Header } from "./Header";
import "./AppShell.css";

export interface WorkspaceSearchContext {
  searchQuery: string;
  setSearchQuery: (value: string) => void;
}

// Wraps every authenticated page except the editor (its own collapsible title bar/toolbar
// already does this job without eating into the grid's vertical space — adding a second,
// persistent global header/sidebar on top of that would cut into exactly the room we spent
// real effort making the grid fill; see EditorPage.tsx / EditorTopBar.tsx).
export function AppShell() {
  const { user, logout } = useAuth();
  // Owned here (not by WorkspacePage) so the header's search box can reach it — only the
  // Workspace page actually uses it, so it's handed down through Outlet's context rather than
  // forcing every shell page to have a search prop it doesn't need.
  const [searchQuery, setSearchQuery] = useState("");
  // Below the mobile breakpoint the sidebar becomes an off-canvas drawer (see AppShell.css) —
  // there was previously no responsive behavior here at all: a fixed 232px sidebar in a
  // non-wrapping flex row squeezed the rest of the page into whatever width was left on a phone
  // screen, forcing heavy text-wrapping and a page far taller than its content needed
  // ("hangs vertically" — reported after testing on a real mobile browser). Desktop is
  // completely unaffected: this state only has a visual effect once the mobile media query in
  // AppShell.css is active.
  const [isMobileNavOpen, setIsMobileNavOpen] = useState(false);
  const location = useLocation();

  // AppShell only ever renders under ProtectedRoute/AdminRoute, both of which already wait for
  // `user` to load before rendering their Outlet.
  if (!user) return null;

  const isWorkspace = location.pathname === "/workspace";

  return (
    <div className="shell">
      <Sidebar
        user={user}
        onLogout={logout}
        isMobileOpen={isMobileNavOpen}
        onMobileClose={() => setIsMobileNavOpen(false)}
      />
      {isMobileNavOpen && (
        <div className="shell-backdrop" onClick={() => setIsMobileNavOpen(false)} />
      )}
      <div className="shell-main">
        <Header
          user={user}
          searchQuery={isWorkspace ? searchQuery : undefined}
          onSearchChange={isWorkspace ? setSearchQuery : undefined}
          onMenuClick={() => setIsMobileNavOpen(true)}
        />
        <div className="shell-content">
          <Outlet context={{ searchQuery, setSearchQuery } satisfies WorkspaceSearchContext} />
        </div>
      </div>
    </div>
  );
}
