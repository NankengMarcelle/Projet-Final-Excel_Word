import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { convertWorksheet } from "../../api/conversions";
import { ApiError } from "../../api/client";
import { useFileDownload } from "../../hooks/useFileDownload";
import { SpinnerIcon, WordDocIcon } from "../icons/EditorIcons";
import { CloseIcon } from "../icons/SettingsIcons";
import type { WorksheetRead } from "../../types/worksheet";
import type { ComputedCellValue } from "../../univer/UniverSheetGrid";
import { copy } from "../../i18n/copy";
import { useLang } from "../../i18n/useLang";
import { useToast } from "../common/NotificationContext";

type Phase = "idle" | "ready" | "downloaded";

// Docked to the right of the grid (see .side-panel in EditorPage.css), same pattern as
// ChildSheetPanel — parked beside the sheet instead of covering it in a centered modal, so the
// sheet being converted stays visible (and pickable, via the dropdown below) without this
// blocking the window.
export function ConvertToWordPanel({
  worksheets,
  onClose,
  getComputedValues,
}: {
  worksheets: WorksheetRead[];
  onClose: () => void;
  getComputedValues: (worksheetId: string) => Promise<ComputedCellValue[]>;
}) {
  const { lang } = useLang();
  const t = copy[lang];
  const { showToast } = useToast();
  const [selectedWorksheetId, setSelectedWorksheetId] = useState(worksheets[0]?.id ?? "");
  const [phase, setPhase] = useState<Phase>("idle");
  const [conversionId, setConversionId] = useState<string | null>(null);
  const [filename, setFilename] = useState<string>("worksheet.docx");

  const { download, isDownloading, error: downloadError } = useFileDownload();

  const mutation = useMutation({
    mutationFn: async () => {
      // Univer's own live, client-side recalculated values for this sheet's formula cells —
      // sent only for this one conversion (not every autosave) so a formula whose on-disk
      // cache went stale/missing still shows a real number instead of literal formula text.
      // See ConvertWorksheetRequest's own docstring on the backend for the full rationale.
      const computedValues = await getComputedValues(selectedWorksheetId);
      return convertWorksheet(selectedWorksheetId, computedValues);
    },
    onSuccess: (response) => {
      setConversionId(response.conversion.id);
      setFilename(response.word_document.filename);
      setPhase("ready");
      showToast(t.conversionReadyToast, "success");
    },
    onError: (err) => {
      showToast(err instanceof ApiError ? String(err.detail) : t.conversionFailedError, "error");
    },
  });

  function handleWorksheetChange(newWorksheetId: string) {
    setSelectedWorksheetId(newWorksheetId);
    setPhase("idle");
    setConversionId(null);
    mutation.reset();
  }

  async function handleDownload() {
    if (!conversionId) return;
    try {
      await download(`/conversions/${conversionId}/download`, filename);
      // The backend deletes the file after streaming it once — this control must not be
      // usable again regardless of what the server would do on a retried request.
      setPhase("downloaded");
      showToast(t.fileDownloadedToast(filename), "success");
    } catch (err) {
      // useFileDownload already captured the error for the inline message below; toast it too
      // since this is exactly the kind of "did anything happen?" moment this app used to leave
      // silent.
      showToast(err instanceof Error ? err.message : t.conversionFailedError, "error");
    }
  }

  return (
    <div role="dialog" aria-label={t.convertModalTitle} className="side-panel">
      <div className="side-panel-header">
        <h2 className="modal-title">{t.convertModalTitle}</h2>
        <button type="button" className="side-panel-close" onClick={onClose} aria-label={t.closeLabel} title={t.closeLabel}>
          <CloseIcon />
        </button>
      </div>

      <div className="side-panel-body">
        <label className="editor-panel-field">
          {t.sheetFieldLabel}
          <select value={selectedWorksheetId} onChange={(e) => handleWorksheetChange(e.target.value)}>
            {worksheets.map((w) => (
              <option key={w.id} value={w.id}>
                {w.name}
              </option>
            ))}
          </select>
        </label>

        {phase === "downloaded" && <p className="editor-panel-note">{t.downloadedNote}</p>}

        {mutation.isError && (
          <p role="alert" className="editor-panel-error">
            {mutation.error instanceof ApiError ? String(mutation.error.detail) : t.conversionFailedError}
          </p>
        )}
        {downloadError && (
          <p role="alert" className="editor-panel-error">
            {downloadError}
          </p>
        )}
      </div>

      <div className="side-panel-footer">
        {phase === "idle" && (
          <>
            <button type="button" className="editor-action-btn" onClick={() => mutation.mutate()} disabled={mutation.isPending}>
              {mutation.isPending ? <SpinnerIcon className="btn-spinner" /> : <WordDocIcon />}{" "}
              {mutation.isPending ? t.convertingStatus : t.convertLabel}
            </button>
            <button type="button" className="editor-action-btn ghost" onClick={onClose}>
              {t.cancelLabel}
            </button>
          </>
        )}

        {phase === "ready" && (
          <>
            <button type="button" className="editor-action-btn" onClick={handleDownload} disabled={isDownloading}>
              {isDownloading && <SpinnerIcon className="btn-spinner" />}
              {isDownloading ? t.downloading : t.downloadFileLabel(filename)}
            </button>
            <button type="button" className="editor-action-btn ghost" onClick={onClose}>
              {t.closeLabel}
            </button>
          </>
        )}

        {phase === "downloaded" && (
          <button type="button" className="editor-action-btn ghost" onClick={onClose}>
            {t.closeLabel}
          </button>
        )}
      </div>
    </div>
  );
}
