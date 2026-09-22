import { useOutletContext } from "react-router-dom";
import { useAuth } from "../auth/useAuth";
import { useLang } from "../i18n/useLang";
import { copy } from "../i18n/copy";
import { UploadForm } from "../components/workspace/UploadForm";
import { WorkbookList } from "../components/workspace/WorkbookList";
import type { WorkspaceSearchContext } from "../components/shell/AppShell";
import "./WorkspacePage.css";

export function WorkspacePage() {
  const { searchQuery } = useOutletContext<WorkspaceSearchContext>();
  const { user } = useAuth();
  const { lang } = useLang();
  const t = copy[lang];

  // full_name is nullable (registration doesn't require it) — fall back to the email's local
  // part rather than greeting someone by their raw email address.
  const displayName = user?.full_name || user?.email.split("@")[0] || "";

  return (
    <main className="workspace-main">
      <section className="workspace-greeting">
        <h1 className="workspace-greeting-heading">{t.workspaceGreeting(displayName)}</h1>
        <p className="workspace-greeting-subtitle">{t.workspaceSubtitle}</p>
      </section>
      <section>
        <h2 className="workspace-section-title">{t.startNewWorkbook}</h2>
        <div className="start-cards">
          <UploadForm />
        </div>
      </section>
      <section>
        <h2 className="workspace-section-title">{t.myWorkbooks}</h2>
        <WorkbookList searchQuery={searchQuery} />
      </section>
    </main>
  );
}
