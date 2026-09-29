import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { MoreVertical } from "lucide-react";
import { deleteUser, listUsers, updateUser } from "../api/admin";
import { useAuth } from "../auth/useAuth";
import { ConfirmDialog } from "../components/common/ConfirmDialog";
import { LoadingState } from "../components/common/LoadingState";
import { useToast } from "../components/common/NotificationContext";
import { copy } from "../i18n/copy";
import { useLang } from "../i18n/useLang";
import type { UserRead } from "../types/auth";
import "./AdminPage.css";

const PAGE_SIZE = 25;
// Waits for a pause in typing before actually querying — searching on every keystroke would
// mean a network round trip per character against a table that's already grown past 3000 rows
// in dev alone.
const SEARCH_DEBOUNCE_MS = 300;

interface RowAction {
  label: string;
  onClick: () => void;
  disabled?: boolean;
  danger?: boolean;
}

// A kebab (⋮) button that opens a small action menu. Portal-rendered to document.body — not a
// dropdown nested in the table row — so it's never clipped by the table card's own rounded-
// corner overflow and always draws above the rest of the page, regardless of where in a long,
// paginated table the row happens to be.
function RowActionsMenu({ label, actions }: { label: string; actions: RowAction[] }) {
  const [open, setOpen] = useState(false);
  const [position, setPosition] = useState<{ top: number; right: number } | null>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    function handlePointerDown(event: MouseEvent) {
      const target = event.target as Node;
      if (menuRef.current?.contains(target) || buttonRef.current?.contains(target)) return;
      setOpen(false);
    }
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") setOpen(false);
    }
    // A scroll would leave a `position: fixed` menu visually detached from the button that
    // opened it — closing on scroll is simpler and safer than re-measuring on every scroll tick.
    function handleScroll() {
      setOpen(false);
    }
    document.addEventListener("mousedown", handlePointerDown);
    document.addEventListener("keydown", handleKeyDown);
    window.addEventListener("scroll", handleScroll, true);
    return () => {
      document.removeEventListener("mousedown", handlePointerDown);
      document.removeEventListener("keydown", handleKeyDown);
      window.removeEventListener("scroll", handleScroll, true);
    };
  }, [open]);

  function toggle() {
    if (!open && buttonRef.current) {
      const rect = buttonRef.current.getBoundingClientRect();
      setPosition({ top: rect.bottom + 6, right: window.innerWidth - rect.right });
    }
    setOpen((value) => !value);
  }

  return (
    <>
      <button
        type="button"
        ref={buttonRef}
        className="admin-kebab-btn"
        onClick={toggle}
        aria-label={label}
        aria-haspopup="menu"
        aria-expanded={open}
      >
        <MoreVertical size={16} />
      </button>
      {open &&
        position &&
        createPortal(
          <div ref={menuRef} className="admin-row-menu" style={{ top: position.top, right: position.right }} role="menu">
            {actions.map((action) => (
              <button
                key={action.label}
                type="button"
                role="menuitem"
                className={`admin-row-menu-item ${action.danger ? "admin-row-menu-item-danger" : ""}`}
                disabled={action.disabled}
                onClick={() => {
                  setOpen(false);
                  action.onClick();
                }}
              >
                {action.label}
              </button>
            ))}
          </div>,
          document.body,
        )}
    </>
  );
}

export function AdminPage() {
  const { lang } = useLang();
  const t = copy[lang];
  const locale = lang === "fr" ? "fr-FR" : "en-US";
  const { user: currentUser } = useAuth();
  const { showToast } = useToast();
  const queryClient = useQueryClient();

  const [searchInput, setSearchInput] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [roleFilter, setRoleFilter] = useState<"" | "user" | "admin">("");
  const [statusFilter, setStatusFilter] = useState<"" | "active" | "inactive">("");
  const [createdAfter, setCreatedAfter] = useState("");
  const [createdBefore, setCreatedBefore] = useState("");
  const [page, setPage] = useState(1);
  const [pendingDelete, setPendingDelete] = useState<UserRead | null>(null);

  useEffect(() => {
    const timer = setTimeout(() => setDebouncedSearch(searchInput), SEARCH_DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [searchInput]);

  // Any filter change makes the current page number meaningless (a narrower result set may not
  // even have that many pages) — always land back on page 1 rather than showing an empty page.
  useEffect(() => {
    setPage(1);
  }, [debouncedSearch, roleFilter, statusFilter, createdAfter, createdBefore]);

  const { data, isLoading, error } = useQuery({
    queryKey: [
      "admin",
      "users",
      { search: debouncedSearch, role: roleFilter, status: statusFilter, createdAfter, createdBefore, page },
    ],
    queryFn: () =>
      listUsers({
        search: debouncedSearch || undefined,
        role: roleFilter || undefined,
        is_active: statusFilter === "" ? undefined : statusFilter === "active",
        created_after: createdAfter || undefined,
        created_before: createdBefore || undefined,
        page,
        page_size: PAGE_SIZE,
      }),
    // Keeps the current page's rows on screen while the next page/filter loads, instead of a
    // full loading-state flash on every pagination click or filter change.
    placeholderData: keepPreviousData,
  });

  const updateMutation = useMutation({
    mutationFn: ({ userId, payload }: { userId: string; payload: Parameters<typeof updateUser>[1] }) =>
      updateUser(userId, payload),
    onSuccess: () => {
      showToast(t.userUpdated, "success");
      queryClient.invalidateQueries({ queryKey: ["admin", "users"] });
    },
    onError: () => showToast(t.userUpdateFailed, "error"),
  });

  const deleteMutation = useMutation({
    mutationFn: (userId: string) => deleteUser(userId),
    onSuccess: () => {
      showToast(t.userDeleted, "success");
      queryClient.invalidateQueries({ queryKey: ["admin", "users"] });
    },
    onError: () => showToast(t.userDeleteFailed, "error"),
  });

  function toggleActive(target: UserRead) {
    updateMutation.mutate({ userId: target.id, payload: { is_active: !target.is_active } });
  }

  function toggleRole(target: UserRead) {
    updateMutation.mutate({
      userId: target.id,
      payload: { role: target.role === "admin" ? "user" : "admin" },
    });
  }

  function handleDelete(target: UserRead) {
    setPendingDelete(target);
  }

  function clearFilters() {
    setSearchInput("");
    setDebouncedSearch("");
    setRoleFilter("");
    setStatusFilter("");
    setCreatedAfter("");
    setCreatedBefore("");
  }

  const hasActiveFilters =
    debouncedSearch !== "" || roleFilter !== "" || statusFilter !== "" || createdAfter !== "" || createdBefore !== "";
  const totalPages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1;

  return (
    <main className="admin-main">
      <h1 className="admin-title">{t.adminUsersTitle}</h1>

      <div className="admin-filters">
        <input
          type="search"
          className="admin-filter-search"
          placeholder={t.searchUsersPlaceholder}
          value={searchInput}
          onChange={(e) => setSearchInput(e.target.value)}
        />
        <select
          className="admin-filter-select"
          value={roleFilter}
          onChange={(e) => setRoleFilter(e.target.value as "" | "user" | "admin")}
        >
          <option value="">{t.filterAllRoles}</option>
          <option value="user">{t.roleUser}</option>
          <option value="admin">{t.roleAdmin}</option>
        </select>
        <select
          className="admin-filter-select"
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value as "" | "active" | "inactive")}
        >
          <option value="">{t.filterAllStatuses}</option>
          <option value="active">{t.statusActive}</option>
          <option value="inactive">{t.statusInactive}</option>
        </select>
        <label className="admin-filter-date">
          {t.filterCreatedAfter}
          <input type="date" value={createdAfter} onChange={(e) => setCreatedAfter(e.target.value)} />
        </label>
        <label className="admin-filter-date">
          {t.filterCreatedBefore}
          <input type="date" value={createdBefore} onChange={(e) => setCreatedBefore(e.target.value)} />
        </label>
        {hasActiveFilters && (
          <button type="button" className="admin-clear-filters" onClick={clearFilters}>
            {t.clearFilters}
          </button>
        )}
      </div>

      {isLoading && <LoadingState message={t.loadingUsers} />}
      {error && (
        <p role="alert" className="admin-status admin-status-error">
          {t.failedToLoadUsers}
        </p>
      )}

      {data && (
        <>
          <p className="admin-results-count">{t.usersFoundCount(data.total)}</p>

          {data.items.length === 0 ? (
            <p className="admin-status">{t.noUsersFound}</p>
          ) : (
            <div className="admin-table-card">
              <table className="admin-table">
                <thead>
                  <tr>
                    <th>{t.colEmail}</th>
                    <th>{t.colFullName}</th>
                    <th>{t.colRole}</th>
                    <th>{t.colStatus}</th>
                    <th>{t.colCreated}</th>
                    <th className="admin-actions-col">{t.colActions}</th>
                  </tr>
                </thead>
                <tbody>
                  {data.items.map((user) => {
                    const isSelf = user.id === currentUser?.id;
                    const pending =
                      (updateMutation.isPending && updateMutation.variables?.userId === user.id) ||
                      (deleteMutation.isPending && deleteMutation.variables === user.id);
                    return (
                      <tr key={user.id}>
                        <td>{user.email}</td>
                        <td>{user.full_name ?? "—"}</td>
                        <td>
                          <span className={`admin-badge ${user.role === "admin" ? "admin-badge-admin" : ""}`}>
                            {user.role === "admin" ? t.roleAdmin : t.roleUser}
                          </span>
                        </td>
                        <td>
                          <span
                            className={`admin-badge ${user.is_active ? "admin-badge-active" : "admin-badge-inactive"}`}
                          >
                            {user.is_active ? t.statusActive : t.statusInactive}
                          </span>
                        </td>
                        <td>{new Date(user.created_at).toLocaleDateString(locale)}</td>
                        <td className="admin-actions-col">
                          {isSelf ? (
                            <span className="admin-badge">{t.youBadge}</span>
                          ) : (
                            <RowActionsMenu
                              label={`${t.colActions} — ${user.email}`}
                              actions={[
                                {
                                  label: user.is_active ? t.actionDeactivate : t.actionActivate,
                                  onClick: () => toggleActive(user),
                                  disabled: pending,
                                },
                                {
                                  label: user.role === "admin" ? t.actionRevokeAdmin : t.actionMakeAdmin,
                                  onClick: () => toggleRole(user),
                                  disabled: pending,
                                },
                                {
                                  label: t.actionDelete,
                                  onClick: () => handleDelete(user),
                                  disabled: pending,
                                  danger: true,
                                },
                              ]}
                            />
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}

          {data.total > 0 && (
            <div className="admin-pagination">
              <button
                type="button"
                className="admin-action-btn"
                disabled={page <= 1}
                onClick={() => setPage((p) => Math.max(1, p - 1))}
              >
                {t.pagePrevious}
              </button>
              <span className="admin-pagination-label">{t.pageOfTotal(page, totalPages)}</span>
              <button
                type="button"
                className="admin-action-btn"
                disabled={page >= totalPages}
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              >
                {t.pageNext}
              </button>
            </div>
          )}
        </>
      )}

      {pendingDelete && (
        <ConfirmDialog
          title={t.confirmDeleteUserTitle}
          message={t.confirmDeleteUser(pendingDelete.email)}
          cancelLabel={t.cancelButton}
          confirmLabel={t.actionDelete}
          danger
          onCancel={() => setPendingDelete(null)}
          onConfirm={() => {
            deleteMutation.mutate(pendingDelete.id);
            setPendingDelete(null);
          }}
        />
      )}
    </main>
  );
}
