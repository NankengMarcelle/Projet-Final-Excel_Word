import { copy } from "../../i18n/copy";
import { useLang } from "../../i18n/useLang";
import "./DeleteSheetWarningModal.css";

interface DeleteSheetWarningModalProps {
  sheetName: string;
  dependentSheetNames: string[];
  onCancel: () => void;
  onConfirm: () => void;
}

// Shown only when the sheet being deleted (via Univer's own native tab menu) is a parent in
// one or more child-sheet relationships — see UniverSheetGrid.tsx's BeforeCommandExecute
// interceptor, which cancels Univer's own delete command to give this modal a chance to warn
// first. Confirming re-issues the same delete, this time allowed through.
export function DeleteSheetWarningModal({
  sheetName,
  dependentSheetNames,
  onCancel,
  onConfirm,
}: DeleteSheetWarningModalProps) {
  const { lang } = useLang();
  const t = copy[lang];

  return (
    <div className="delete-sheet-overlay" onClick={onCancel}>
      <div
        role="alertdialog"
        aria-label={t.deleteSheetWarningTitle}
        className="delete-sheet-card"
        onClick={(e) => e.stopPropagation()}
      >
        <h2>{t.deleteSheetWarningTitle}</h2>
        <p className="delete-sheet-target">{sheetName}</p>
        <p>{t.deleteSheetWarningBody}</p>
        <ul className="delete-sheet-dependents">
          {dependentSheetNames.map((name) => (
            <li key={name}>{name}</li>
          ))}
        </ul>
        <div className="delete-sheet-actions">
          <button type="button" className="delete-sheet-cancel-btn" onClick={onCancel}>
            {t.deleteSheetCancel}
          </button>
          <button type="button" className="delete-sheet-confirm-btn" onClick={onConfirm}>
            {t.deleteSheetConfirm}
          </button>
        </div>
      </div>
    </div>
  );
}
