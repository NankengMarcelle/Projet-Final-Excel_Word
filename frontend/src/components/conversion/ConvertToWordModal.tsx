import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { convertWorksheet } from "../../api/conversions";
import { ApiError } from "../../api/client";
import { useFileDownload } from "../../hooks/useFileDownload";
import { SpinnerIcon, WordDocIcon } from "../icons/EditorIcons";
import type { WorksheetRead } from "../../types/worksheet";

type Phase = "idle" | "ready" | "downloaded";

// Moved from an always-visible inline "Convert to Word: [dropdown] [Convert]" strip in the
// toolbar into this on-demand popup — the sheet picker only needs to exist while the user is
// actually converting something, not permanently taking up space in the title bar.
export function ConvertToWordModal({ worksheets, onClose }: { worksheets: WorksheetRead[]; onClose: () => void }) {
  const [selectedWorksheetId, setSelectedWorksheetId] = useState(worksheets[0]?.id ?? "");
  const [phase, setPhase] = useState<Phase>("idle");
  const [conversionId, setConversionId] = useState<string | null>(null);
  const [filename, setFilename] = useState<string>("worksheet.docx");

  const { download, isDownloading, error: downloadError } = useFileDownload();

  const mutation = useMutation({
    mutationFn: () => convertWorksheet(selectedWorksheetId),
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
      <div role="dialog" aria-label="Convert to Word" className="modal-card" onClick={(event) => event.stopPropagation()}>
        <h2 className="modal-title">Convert to Word</h2>

        <label className="editor-panel-field">
          Sheet
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
              {mutation.isPending ? "Converting..." : "Convert"}
            </button>
            <button type="button" className="editor-action-btn ghost" onClick={onClose}>
              Cancel
            </button>
          </div>
        )}

        {phase === "ready" && (
          <div className="modal-actions">
            <button type="button" className="editor-action-btn" onClick={handleDownload} disabled={isDownloading}>
              {isDownloading && <SpinnerIcon className="btn-spinner" />}
              {isDownloading ? "Downloading..." : `Download ${filename}`}
            </button>
            <button type="button" className="editor-action-btn ghost" onClick={onClose}>
              Close
            </button>
          </div>
        )}

        {phase === "downloaded" && (
          <>
            <p className="editor-panel-note">Downloaded — convert again for a new copy.</p>
            <div className="modal-actions">
              <button type="button" className="editor-action-btn ghost" onClick={onClose}>
                Close
              </button>
            </div>
          </>
        )}

        {mutation.isError && (
          <p role="alert" className="editor-panel-error">
            {mutation.error instanceof ApiError ? String(mutation.error.detail) : "Conversion failed"}
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
