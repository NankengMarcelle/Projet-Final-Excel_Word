import { useQuery } from "@tanstack/react-query";
import { listUsers } from "../api/admin";
import { LoadingState } from "../components/common/LoadingState";
import { copy } from "../i18n/copy";
import { useLang } from "../i18n/useLang";
import "./AdminPage.css";

export function AdminPage() {
  const { lang } = useLang();
  const t = copy[lang];
  const locale = lang === "fr" ? "fr-FR" : "en-US";
  const { data: users, isLoading, error } = useQuery({
    queryKey: ["admin", "users"],
    queryFn: listUsers,
  });

  return (
    <main className="admin-main">
      <h1 className="admin-title">{t.adminUsersTitle}</h1>

      {isLoading && <LoadingState message={t.loadingUsers} />}
      {error && (
        <p role="alert" className="admin-status admin-status-error">
          {t.failedToLoadUsers}
        </p>
      )}

      {users && (
        <div className="admin-table-card">
          <table className="admin-table">
            <thead>
              <tr>
                <th>{t.colEmail}</th>
                <th>{t.colFullName}</th>
                <th>{t.colRole}</th>
                <th>{t.colStatus}</th>
                <th>{t.colCreated}</th>
              </tr>
            </thead>
            <tbody>
              {users.map((user) => (
                <tr key={user.id}>
                  <td>{user.email}</td>
                  <td>{user.full_name ?? "—"}</td>
                  <td>
                    <span className={`admin-badge ${user.role === "admin" ? "admin-badge-admin" : ""}`}>
                      {user.role === "admin" ? t.roleAdmin : t.roleUser}
                    </span>
                  </td>
                  <td>
                    <span className={`admin-badge ${user.is_active ? "admin-badge-active" : "admin-badge-inactive"}`}>
                      {user.is_active ? t.statusActive : t.statusInactive}
                    </span>
                  </td>
                  <td>{new Date(user.created_at).toLocaleDateString(locale)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </main>
  );
}
