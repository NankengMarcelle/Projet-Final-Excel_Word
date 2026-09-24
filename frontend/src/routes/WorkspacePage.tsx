import { Link, useOutletContext } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { useAuth } from "../auth/useAuth";
import { useLang } from "../i18n/useLang";
import { copy } from "../i18n/copy";
import { listWorkbooks } from "../api/workbooks";
import { UploadForm } from "../components/workspace/UploadForm";
import { WorkbookList } from "../components/workspace/WorkbookList";
import type { WorkspaceSearchContext } from "../components/shell/AppShell";
import "./WorkspacePage.css";

// How many recent workbooks the home page shows before pointing to the full list — Google
// Sheets' own home does the same thing (a handful of "Today"/"Previous 30 days" rows, a full
// Drive view for everything else) rather than one page trying to be both a quick daily landing
// spot and a complete file browser.
const RECENT_WORKBOOKS_LIMIT = 5;

export function WorkspacePage() {
  const { searchQuery } = useOutletContext<WorkspaceSearchContext>();
  const { user } = useAuth();
  const { lang } = useLang();
  const t = copy[lang];

  // Same query key WorkbookList itself uses (["workbooks"]) — React Query dedupes this to the
  // already-cached fetch, so this doesn't cost a second request. Only used to decide whether
  // "See all workbooks" is worth showing at all (no link to a fuller list when there isn't one).
  const { data: workbooks } = useQuery({ queryKey: ["workbooks"], queryFn: listWorkbooks });
  const hasMoreWorkbooks = (workbooks?.length ?? 0) > RECENT_WORKBOOKS_LIMIT;

  // full_name is nullable (registration doesn't require it) — fall back to the email's local
  // part rather than greeting someone by their raw email address.
  const displayName = user?.full_name || user?.email.split("@")[0] || "";

  // Two flat, full-bleed zones (like Google Sheets' own home), not floating boxed cards — a
  // bordered/shadowed card around a couple of controls reads as generic "component library"
  // chrome; a plain color change between sections is quieter and, per Sheets' own precedent,
  // still reads as two distinct areas without needing a border to say so.
  return (
    <main className="workspace-main">
      <div className="workspace-header-section">
        <div className="workspace-inner">
          <p className="workspace-greeting-line">{t.workspaceGreeting(displayName)}</p>
          <p className="workspace-subtitle">{t.workspaceSubtitle}</p>
          <div className="workspace-upload-row">
            <h2 className="workspace-upload-title">{t.startNewWorkbook}</h2>
            <UploadForm />
          </div>
        </div>
      </div>

      <div className="workspace-list-section">
        <div className="workspace-inner">
          <div className="workspace-list-header">
            <h1 className="workspace-list-title">{t.myWorkbooks}</h1>
          </div>
          {/* The cap only applies when the user isn't actively searching — a search that
              matched 6 files but only showed 5 with no way to reach the 6th would be a worse
              bug than the cap this feature exists to add. */}
          <WorkbookList searchQuery={searchQuery} limit={searchQuery ? undefined : RECENT_WORKBOOKS_LIMIT} />
          {hasMoreWorkbooks && !searchQuery && (
            <Link to="/workspace/all" className="workspace-see-more">
              {t.seeMoreWorkbooks}
            </Link>
          )}
        </div>
      </div>
    </main>
  );
}
