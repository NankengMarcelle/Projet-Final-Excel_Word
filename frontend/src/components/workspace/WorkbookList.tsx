import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { listWorkbooks } from "../../api/workbooks";
import { WorkbookRow } from "./WorkbookRow";
import { LoadingState } from "../common/LoadingState";
import type { WorkbookRead } from "../../types/workbook";
import { copy } from "../../i18n/copy";
import { useLang } from "../../i18n/useLang";

const DAY_MS = 24 * 60 * 60 * 1000;

// Internal keys only — never rendered directly (that made the group headers immune to the
// language toggle, since "Today"/"Earlier" etc. were both the Record key AND the displayed
// text). The actual label is looked up from `copy` at render time via GROUP_LABEL_KEYS below.
type RecencyGroup = "today" | "previous7days" | "earlier";

function groupByRecency(workbooks: WorkbookRead[]): { group: RecencyGroup; items: WorkbookRead[] }[] {
  const now = Date.now();
  const today = new Date().toDateString();
  const groups: Record<RecencyGroup, WorkbookRead[]> = { today: [], previous7days: [], earlier: [] };

  for (const workbook of workbooks) {
    const created = new Date(workbook.created_at);
    if (created.toDateString() === today) {
      groups.today.push(workbook);
    } else if (now - created.getTime() < 7 * DAY_MS) {
      groups.previous7days.push(workbook);
    } else {
      groups.earlier.push(workbook);
    }
  }

  return (Object.entries(groups) as [RecencyGroup, WorkbookRead[]][])
    .filter(([, items]) => items.length > 0)
    .map(([group, items]) => ({ group, items }));
}

export function WorkbookList({ searchQuery }: { searchQuery: string }) {
  const { lang } = useLang();
  const t = copy[lang];
  const GROUP_LABELS: Record<RecencyGroup, string> = {
    today: t.groupToday,
    previous7days: t.groupPrevious7Days,
    earlier: t.groupEarlier,
  };

  const {
    data: workbooks,
    isLoading,
    error,
  } = useQuery({
    queryKey: ["workbooks"],
    queryFn: listWorkbooks,
  });

  const filtered = useMemo(() => {
    if (!workbooks) return [];
    const query = searchQuery.trim().toLowerCase();
    return query ? workbooks.filter((wb) => wb.filename.toLowerCase().includes(query)) : workbooks;
  }, [workbooks, searchQuery]);

  const groups = useMemo(() => groupByRecency(filtered), [filtered]);

  if (isLoading) return <LoadingState message={t.loadingWorkbooks} />;
  if (error) return <p role="alert" className="workspace-status">{t.failedToLoadWorkbooks}</p>;

  if (!workbooks || workbooks.length === 0) {
    return (
      <div className="workspace-empty">
        <p>{t.noWorkbooksYet}</p>
      </div>
    );
  }

  if (filtered.length === 0) {
    return (
      <div className="workspace-empty">
        <p>{t.noWorkbooksMatch(searchQuery)}</p>
      </div>
    );
  }

  return (
    <div className="workbook-table">
      <div className="workbook-columns">
        <span>{t.colName}</span>
        <span>{t.colSize}</span>
        <span>{t.colImported}</span>
        <span />
      </div>
      {groups.map(({ group, items }) => (
        <div key={group}>
          <div className="workbook-group-label">{GROUP_LABELS[group]}</div>
          {items.map((workbook) => (
            <WorkbookRow key={workbook.id} workbook={workbook} />
          ))}
        </div>
      ))}
    </div>
  );
}
