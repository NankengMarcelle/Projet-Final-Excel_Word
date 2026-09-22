import { copy } from "../../i18n/copy";
import { useLang } from "../../i18n/useLang";
import type { WorksheetData } from "../../types/worksheet";

interface EditorFooterProps {
  // undefined only very briefly (activeSheetId set from initialSheets[0], which always exists
  // once this component mounts at all — EditorWorkbookReady only renders once worksheets have
  // loaded), so this renders an empty stats slot rather than nothing while that resolves.
  activeSheet: WorksheetData | undefined;
}

export function EditorFooter({ activeSheet }: EditorFooterProps) {
  const { lang } = useLang();
  const t = copy[lang];

  return (
    <div className="editor-footer">
      <span>{t.editorFooterCopyright}</span>
      {activeSheet && (
        <span>
          {t.editorReady} • {t.editorActiveSheet(activeSheet.name, activeSheet.max_row, activeSheet.max_column)}
        </span>
      )}
    </div>
  );
}
