import { Link, useOutletContext } from "react-router-dom";
import { ArrowLeft } from "lucide-react";
import { useLang } from "../i18n/useLang";
import { copy } from "../i18n/copy";
import { WorkbookList } from "../components/workspace/WorkbookList";
import type { WorkspaceSearchContext } from "../components/shell/AppShell";
import "./WorkspacePage.css";

// The uncapped counterpart to WorkspacePage's own recent-files list (see its "See all
// workbooks" link) — same flat list section, same search, just no `limit` on WorkbookList.
export function AllWorkbooksPage() {
  const { searchQuery } = useOutletContext<WorkspaceSearchContext>();
  const { lang } = useLang();
  const t = copy[lang];

  return (
    <main className="workspace-main">
      <div className="workspace-header-section">
        <div className="workspace-inner">
          <Link to="/workspace" className="workspace-back-link">
            <ArrowLeft size={14} /> {t.backToWorkspaceLink}
          </Link>
        </div>
      </div>
      <div className="workspace-list-section">
        <div className="workspace-inner">
          <div className="workspace-list-header">
            <h1 className="workspace-list-title">{t.allWorkbooksTitle}</h1>
          </div>
          <WorkbookList searchQuery={searchQuery} />
        </div>
      </div>
    </main>
  );
}
