import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { createChildSheet } from "../../api/childSheets";
import { ApiError } from "../../api/client";
import { SpinnerIcon } from "../icons/EditorIcons";
import type { ComputedCellValue } from "../../univer/UniverSheetGrid";
import type { WorksheetRead } from "../../types/worksheet";
import { copy } from "../../i18n/copy";
import { useLang } from "../../i18n/useLang";
import {
  ChildSheetSourceSection,
  createEmptySourceFormState,
  type SourceFormState,
} from "./ChildSheetSourceSection";

export function ChildSheetModal({
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
  getComputedValues: (worksheetId: string) => ComputedCellValue[];
}) {
  const { lang } = useLang();
  const t = copy[lang];
  const queryClient = useQueryClient();
  const [childSheetName, setChildSheetName] = useState("");
  const [sources, setSources] = useState<SourceFormState[]>([
    createEmptySourceFormState(defaultParentWorksheetId),
  ]);
  const [error, setError] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: () =>
      createChildSheet(workbookId, {
        child_sheet_name: childSheetName,
        sources: sources.map((source) => ({
          parent_worksheet_id: source.parentWorksheetId,
          header_start_row: source.headerStartRow,
          header_end_row: source.headerEndRow,
          selected_columns: source.selectedColumns,
          filter_criteria: source.filterGroup,
          // Each parent's formula cells may have no valid backend-side cache at all (openpyxl
          // has no formula engine) — Univer, already rendering that parent live, has the real
          // answer.
          computed_values: getComputedValues(source.parentWorksheetId),
        })),
      }),
    onSuccess: (response) => {
      void queryClient.invalidateQueries({ queryKey: ["workbooks", workbookId] });
      onCreated(response.worksheet.id);
    },
    onError: (err) => {
      setError(err instanceof ApiError ? String(err.detail) : "Failed to create child sheet");
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
      setError("Child sheet name is required");
      return;
    }
    for (const source of sources) {
      if (source.headerEndRow < source.headerStartRow) {
        setError("Header end row must be greater than or equal to header start row");
        return;
      }
      if (source.selectedColumns.length === 0) {
        setError("Select at least one column for every sheet");
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
    <div className="modal-overlay" onClick={onClose}>
      <div
        role="dialog"
        aria-label="Create child sheet"
        className="modal-card"
        onClick={(event) => event.stopPropagation()}
      >
        <h2 className="modal-title">Create child sheet</h2>
        <label className="editor-panel-field">
          Child sheet name
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
            sourceLabel={`Sheet ${index + 1}`}
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

        <div className="modal-actions">
          <button type="button" className="editor-action-btn" onClick={handleSubmit} disabled={mutation.isPending}>
            {mutation.isPending && <SpinnerIcon className="btn-spinner" />}
            {mutation.isPending ? "Creating..." : "Create"}
          </button>
          <button type="button" className="editor-action-btn ghost" onClick={onClose}>
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
}
