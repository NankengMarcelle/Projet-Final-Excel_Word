import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { convertWorksheet } from "../../api/conversions";
import { ApiError } from "../../api/client";
import { useFileDownload } from "../../hooks/useFileDownload";
import { SpinnerIcon, WordDocIcon } from "../icons/EditorIcons";
import type { WorksheetRead } from "../../types/worksheet";
import type { ComputedCellValue } from "../../univer/UniverSheetGrid";
import { copy } from "../../i18n/copy";
import { useLang } from "../../i18n/useLang";

type Phase = "idle" | "ready" | "downloaded";

// Moved from an always-visible inline "Convert to Word: [dropdown] [Convert]" strip in the
// toolbar into this on-demand popup — the sheet picker only needs to exist while the user is
// actually converting something, not permanently taking up space in the title bar.
export function ConvertToWordModal({
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
    } catch {
      // useFileDownload already captured the error for display below.
    }
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div role="dialog" aria-label={t.convertModalTitle} className="modal-card" onClick={(event) => event.stopPropagation()}>
        <h2 className="modal-title">{t.convertModalTitle}</h2>

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

        {phase === "idle" && (
          <div className="modal-actions">
            <button type="button" className="editor-action-btn" onClick={() => mutation.mutate()} disabled={mutation.isPending}>
              {mutation.isPending ? <SpinnerIcon className="btn-spinner" /> : <WordDocIcon />}{" "}
              {mutation.isPending ? t.convertingStatus : t.convertLabel}
            </button>
            <button type="button" className="editor-action-btn ghost" onClick={onClose}>
              {t.cancelLabel}
            </button>
          </div>
        )}

        {phase === "ready" && (
          <div className="modal-actions">
            <button type="button" className="editor-action-btn" onClick={handleDownload} disabled={isDownloading}>
              {isDownloading && <SpinnerIcon className="btn-spinner" />}
              {isDownloading ? t.downloading : t.downloadFileLabel(filename)}
            </button>
            <button type="button" className="editor-action-btn ghost" onClick={onClose}>
              {t.closeLabel}
            </button>
          </div>
        )}

        {phase === "downloaded" && (
          <>
            <p className="editor-panel-note">{t.downloadedNote}</p>
            <div className="modal-actions">
              <button type="button" className="editor-action-btn ghost" onClick={onClose}>
                {t.closeLabel}
              </button>
            </div>
          </>
        )}

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
    </div>
  );
}
