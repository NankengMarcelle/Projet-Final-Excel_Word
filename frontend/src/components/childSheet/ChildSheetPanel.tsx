import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { createChildSheet } from "../../api/childSheets";
import { ApiError } from "../../api/client";
import { SpinnerIcon } from "../icons/EditorIcons";
import { CloseIcon } from "../icons/SettingsIcons";
import type { ComputedCellValue } from "../../univer/UniverSheetGrid";
import type { WorksheetRead } from "../../types/worksheet";
import { copy } from "../../i18n/copy";
import { useLang } from "../../i18n/useLang";
import { useToast } from "../common/NotificationContext";
import {
  ChildSheetSourceSection,
  createEmptySourceFormState,
  type SourceFormState,
} from "./ChildSheetSourceSection";

// Docked to the right of the grid (see .side-panel in EditorPage.css) rather than a
// centered modal over a dark backdrop — the reference for this was Excel's own "Queries &
// Connections" pane, which parks beside the sheet instead of covering it, so the columns a
// source sheet actually has stay visible (and the sheet itself stays usable) while filling out
// this form, without needing to close it just to go check.
export function ChildSheetPanel({
  workbookId,
  worksheets,
  defaultParentWorksheetId,
  onClose,
  onCreated,
  getComputedValues,
}: {
  workbookId: string;
  worksheets: WorksheetRead[];
  defaultParentWorksheetId: string;
  onClose: () => void;
  onCreated: (childWorksheetId: string) => void;
  getComputedValues: (worksheetId: string) => Promise<ComputedCellValue[]>;
}) {
  const { lang } = useLang();
  const t = copy[lang];
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const [childSheetName, setChildSheetName] = useState("");
  const [sources, setSources] = useState<SourceFormState[]>([
    createEmptySourceFormState(defaultParentWorksheetId),
  ]);
  const [error, setError] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: async () => {
      const sourcesPayload = await Promise.all(
        sources.map(async (source) => ({
          parent_worksheet_id: source.parentWorksheetId,
          header_start_row: source.headerStartRow,
          header_end_row: source.headerEndRow,
          selected_columns: source.selectedColumns,
          filter_criteria: source.filterGroup,
          // Each parent's formula cells may have no valid backend-side cache at all (openpyxl
          // has no formula engine) — Univer, already rendering that parent live, has the real
          // answer. Awaited: this forces (and waits out) a full recalculation first, see
          // getComputedValues' own comment for why that's not optional.
          computed_values: await getComputedValues(source.parentWorksheetId),
        }))
      );
      return createChildSheet(workbookId, {
        child_sheet_name: childSheetName,
        sources: sourcesPayload,
      });
    },
    onSuccess: (response) => {
      void queryClient.invalidateQueries({ queryKey: ["workbooks", workbookId] });
      showToast(t.childSheetCreatedToast(childSheetName), "success");
      onCreated(response.worksheet.id);
    },
    onError: (err) => {
      const message = err instanceof ApiError ? String(err.detail) : t.createChildSheetFailedError;
      setError(message);
      showToast(message, "error");
    },
  });

  function updateSource(index: number, next: SourceFormState) {
    setSources((prev) => prev.map((source, i) => (i === index ? next : source)));
  }

  function addSource() {
    setSources((prev) => [...prev, createEmptySourceFormState(defaultParentWorksheetId)]);
  }

  function removeSource(index: number) {
    setSources((prev) => prev.filter((_, i) => i !== index));
  }

  function handleSubmit() {
    setError(null);
    if (!childSheetName.trim()) {
      setError(t.childSheetNameRequiredError);
      return;
    }
    for (const source of sources) {
      if (source.headerEndRow < source.headerStartRow) {
        setError(t.headerRowRangeError);
        return;
      }
      if (source.selectedColumns.length === 0) {
        setError(t.selectAtLeastOneColumnError);
        return;
      }
    }
    const columnCounts = new Set(sources.map((source) => source.selectedColumns.length));
    if (columnCounts.size > 1) {
      setError(t.columnCountMismatchError);
      return;
    }
    mutation.mutate();
  }

  return (
    <div role="dialog" aria-label={t.createChildSheetTitle} className="side-panel">
      <div className="side-panel-header">
        <h2 className="modal-title">{t.createChildSheetTitle}</h2>
        <button type="button" className="side-panel-close" onClick={onClose} aria-label={t.closeLabel} title={t.closeLabel}>
          <CloseIcon />
        </button>
      </div>

      <div className="side-panel-body">
        <label className="editor-panel-field">
          {t.childSheetNameLabel}
          <input type="text" value={childSheetName} onChange={(e) => setChildSheetName(e.target.value)} />
        </label>

        {sources.map((source, index) => (
          <ChildSheetSourceSection
            key={index}
            workbookId={workbookId}
            worksheets={worksheets}
            value={source}
            onChange={(next) => updateSource(index, next)}
            onRemove={() => removeSource(index)}
            showRemove={sources.length > 1}
            sourceLabel={t.sheetNumberLabel(index + 1)}
          />
        ))}

        <button type="button" className="editor-action-btn ghost" onClick={addSource}>
          {t.addAnotherSheetLabel}
        </button>

        {error && (
          <p role="alert" className="editor-panel-error">
            {error}
          </p>
        )}
      </div>

      <div className="side-panel-footer">
        <button type="button" className="editor-action-btn" onClick={handleSubmit} disabled={mutation.isPending}>
          {mutation.isPending && <SpinnerIcon className="btn-spinner" />}
          {mutation.isPending ? t.creatingLabel : t.createLabel}
        </button>
        <button type="button" className="editor-action-btn ghost" onClick={onClose}>
          {t.cancelLabel}
        </button>
      </div>
    </div>
  );
}
