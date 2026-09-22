import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { renameWorkbook } from "../../api/workbooks";
import type { SaveStatus } from "../../hooks/useDebouncedAutosave";
import { ArrowLeftIcon, ChevronIcon, PlusIcon, SaveIcon, WordDocIcon } from "../icons/EditorIcons";
import { SpreadsheetFileIcon } from "../icons/WorkspaceIcons";
import { GearIcon } from "../icons/SettingsIcons";
import { SettingsModal } from "../settings/SettingsModal";
import { ConvertToWordModal } from "../conversion/ConvertToWordModal";
import { SaveStatusIndicator } from "./SaveStatusIndicator";
import { ChildSheetSyncPanel } from "../sync/ChildSheetSyncPanel";
import type { ComputedCellValue } from "../../univer/UniverSheetGrid";
import type { WorksheetRead } from "../../types/worksheet";
import { copy } from "../../i18n/copy";
import { useLang } from "../../i18n/useLang";

interface EditorTopBarProps {
  workbookId: string;
  filename: string;
  saveStatus: SaveStatus;
  onSave: () => void;
  worksheets: WorksheetRead[];
  canCreateChildSheet: boolean;
  onCreateChildSheet: () => void;
  onChildSheetSynced: () => void;
  onToggleCollapsed: () => void;
  getComputedValues: (worksheetId: string) => ComputedCellValue[];
}

// A single row now, not two stacked bars: filename/Save on the left (Save leftmost among the
// action buttons, mirroring Excel's own title bar), workbook-level actions (Create Child Sheet,
// Convert to Word) pushed to the right, Settings and the collapse toggle at the far end. Convert
// to Word used to be an always-visible "label + dropdown + button" strip; it's now a single
// button that opens ConvertToWordModal, where the sheet picker only exists while actually
// converting something.
export function EditorTopBar({
  workbookId,
  filename,
  saveStatus,
  onSave,
  worksheets,
  canCreateChildSheet,
  onCreateChildSheet,
  onChildSheetSynced,
  onToggleCollapsed,
  getComputedValues,
}: EditorTopBarProps) {
  const { lang } = useLang();
  const t = copy[lang];
  const queryClient = useQueryClient();
  const [isRenaming, setIsRenaming] = useState(false);
  const [nameDraft, setNameDraft] = useState(filename);
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const [isConvertOpen, setIsConvertOpen] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  // The workbook query can refetch/rename from elsewhere (e.g. this same rename, or a future
  // background refetch) — keep the draft in sync whenever not actively editing it.
  useEffect(() => {
    if (!isRenaming) setNameDraft(filename);
  }, [filename, isRenaming]);

  useEffect(() => {
    if (isRenaming) inputRef.current?.select();
  }, [isRenaming]);

  const renameMutation = useMutation({
    mutationFn: (nextFilename: string) => renameWorkbook(workbookId, nextFilename),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["workbooks", workbookId] });
      void queryClient.invalidateQueries({ queryKey: ["workbooks"] });
    },
    onError: () => setNameDraft(filename),
  });

  function commitRename() {
    setIsRenaming(false);
    const trimmed = nameDraft.trim();
    if (trimmed && trimmed !== filename) {
      renameMutation.mutate(trimmed);
    } else {
      setNameDraft(filename);
    }
  }

  return (
    <div className="editor-topbar-row">
      <Link to="/workspace" className="editor-back-btn" aria-label={t.backToWorkspace}>
        <ArrowLeftIcon />
      </Link>

      <button type="button" className="editor-save-btn" onClick={onSave} disabled={saveStatus === "saving"} title={t.saveNowTooltip}>
        <SaveIcon /> {t.saveButton}
      </button>
      <SaveStatusIndicator status={saveStatus} />

      <span className="editor-topbar-divider" />

      <SpreadsheetFileIcon className="editor-title-icon" />
      {isRenaming ? (
        <input
          ref={inputRef}
          className="editor-filename-input"
          value={nameDraft}
          onChange={(event) => setNameDraft(event.target.value)}
          onBlur={commitRename}
          onKeyDown={(event) => {
            if (event.key === "Enter") {
              event.preventDefault();
              commitRename();
            }
            if (event.key === "Escape") {
              setNameDraft(filename);
              setIsRenaming(false);
            }
          }}
        />
      ) : (
        <button type="button" className="editor-filename" onClick={() => setIsRenaming(true)} title={t.renameWorkbookTooltip}>
          {filename}
        </button>
      )}

      <div className="editor-topbar-spacer" />

      {canCreateChildSheet && (
        <button type="button" className="editor-action-btn small" onClick={onCreateChildSheet}>
          <PlusIcon /> {t.childSheetLabel}
        </button>
      )}
      <ChildSheetSyncPanel
        workbookId={workbookId}
        worksheets={worksheets}
        onSynced={onChildSheetSynced}
        getComputedValues={getComputedValues}
      />
      {worksheets.length > 0 && (
        <button type="button" className="editor-action-btn small" onClick={() => setIsConvertOpen(true)}>
          <WordDocIcon /> {t.convertLabel}
        </button>
      )}

      <button
        type="button"
        className="editor-settings-btn"
        onClick={() => setIsSettingsOpen(true)}
        aria-label={t.settings}
        title={t.settings}
      >
        <GearIcon />
      </button>

      <button
        type="button"
        className="editor-collapse-toggle"
        onClick={onToggleCollapsed}
        aria-label={t.hideTitleBar}
        title={t.hideTitleBar}
      >
        <ChevronIcon className="flip" />
      </button>

      {isSettingsOpen && <SettingsModal onClose={() => setIsSettingsOpen(false)} />}
      {isConvertOpen && <ConvertToWordModal worksheets={worksheets} onClose={() => setIsConvertOpen(false)} />}
    </div>
  );
}
