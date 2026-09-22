import { useQuery } from "@tanstack/react-query";
import { listWorksheetColumns } from "../../api/worksheets";
import type { WorksheetRead } from "../../types/worksheet";
import type { FilterConditionGroup } from "../../types/filter";
import { copy } from "../../i18n/copy";
import { useLang } from "../../i18n/useLang";
import { ColumnPicker } from "./ColumnPicker";
import { FilterGroupEditor } from "./FilterGroupEditor";

// One source sheet's own form state — mirrors ChildSheetSourceConfig (types/sheetRelationship.ts)
// minus computed_values, which is gathered separately at submit time from the live grid.
export interface SourceFormState {
  parentWorksheetId: string;
  headerStartRow: number;
  headerEndRow: number;
  selectedColumns: number[];
  filterGroup: FilterConditionGroup;
}

export function createEmptySourceFormState(defaultParentWorksheetId: string): SourceFormState {
  return {
    parentWorksheetId: defaultParentWorksheetId,
    headerStartRow: 1,
    headerEndRow: 1,
    selectedColumns: [],
    filterGroup: { logic: "AND", conditions: [] },
  };
}

// One contributing sheet's config form — parent-sheet select, header range, column picker,
// filter editor. Rendered once per source in ChildSheetModal (create: N sections building up
// one request) — fully controlled, no internal state of its own, so the parent form owns
// everything and can validate across sections (e.g. matching column counts) before submitting.
export function ChildSheetSourceSection({
  workbookId,
  worksheets,
  value,
  onChange,
  onRemove,
  showRemove,
  sourceLabel,
}: {
  workbookId: string;
  worksheets: WorksheetRead[];
  value: SourceFormState;
  onChange: (next: SourceFormState) => void;
  onRemove?: () => void;
  showRemove: boolean;
  sourceLabel: string;
}) {
  const { lang } = useLang();
  const t = copy[lang];
  const headerRangeValid = value.headerStartRow >= 1 && value.headerEndRow >= value.headerStartRow;

  const { data: columns = [] } = useQuery({
    queryKey: [
      "worksheet-columns",
      workbookId,
      value.parentWorksheetId,
      value.headerStartRow,
      value.headerEndRow,
    ],
    queryFn: () =>
      listWorksheetColumns(workbookId, value.parentWorksheetId, value.headerStartRow, value.headerEndRow),
    enabled: headerRangeValid,
  });

  const originalWorksheets = worksheets.filter((w) => w.sheet_type === "original");

  // Selected columns/filters are specific to the previous parent's (or header range's) columns
  // — an index that made sense before might now point at a different column, or none at all,
  // so it's safer to reset than to silently carry over a now-meaningless selection.
  function updateAndResetSelection(patch: Partial<SourceFormState>) {
    onChange({ ...value, ...patch, selectedColumns: [], filterGroup: { logic: "AND", conditions: [] } });
  }

  return (
    <div className="child-sheet-source-section">
      <div className="child-sheet-source-section-header">
        <h3 className="modal-subtitle">{sourceLabel}</h3>
        {showRemove && onRemove && (
          <button type="button" className="editor-action-btn small ghost" onClick={onRemove}>
            {t.removeSheetLabel}
          </button>
        )}
      </div>

      <label className="editor-panel-field">
        Parent sheet
        <select
          value={value.parentWorksheetId}
          onChange={(e) => updateAndResetSelection({ parentWorksheetId: e.target.value })}
        >
          {originalWorksheets.map((w) => (
            <option key={w.id} value={w.id}>
              {w.name}
            </option>
          ))}
        </select>
      </label>

      <label className="editor-panel-field">
        Header start row
        <input
          type="number"
          min={1}
          value={value.headerStartRow}
          onChange={(e) => updateAndResetSelection({ headerStartRow: Number(e.target.value) })}
        />
      </label>
      <label className="editor-panel-field">
        Header end row
        <input
          type="number"
          min={1}
          value={value.headerEndRow}
          onChange={(e) => updateAndResetSelection({ headerEndRow: Number(e.target.value) })}
        />
      </label>

      <ColumnPicker
        columns={columns}
        selected={value.selectedColumns}
        onChange={(selectedColumns) => onChange({ ...value, selectedColumns })}
      />

      <h4 className="modal-subtitle">Filter criteria</h4>
      <FilterGroupEditor
        group={value.filterGroup}
        columns={columns}
        onChange={(filterGroup) => onChange({ ...value, filterGroup })}
      />
    </div>
  );
}
