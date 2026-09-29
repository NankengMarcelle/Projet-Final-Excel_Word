import "./ConfirmDialog.css";

interface ConfirmDialogProps {
  title: string;
  message: string;
  cancelLabel: string;
  confirmLabel: string;
  danger?: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}

// A real in-app dialog rather than window.confirm() — the native dialog turned out to be
// unreliable in practice (confirmed live: it can be silently auto-dismissed depending on the
// browser/embedding context, which looked from the outside like "clicking Delete does
// nothing" with no error at all). This renders in normal React state instead, so it behaves
// the same everywhere and can be styled/localized like the rest of the app.
export function ConfirmDialog({
  title,
  message,
  cancelLabel,
  confirmLabel,
  danger = false,
  onCancel,
  onConfirm,
}: ConfirmDialogProps) {
  return (
    <div className="confirm-dialog-overlay" onClick={onCancel}>
      <div role="alertdialog" aria-label={title} className="confirm-dialog-card" onClick={(e) => e.stopPropagation()}>
        <h2 className={danger ? "confirm-dialog-title-danger" : undefined}>{title}</h2>
        <p>{message}</p>
        <div className="confirm-dialog-actions">
          <button type="button" className="confirm-dialog-cancel-btn" onClick={onCancel}>
            {cancelLabel}
          </button>
          <button
            type="button"
            className={danger ? "confirm-dialog-confirm-btn-danger" : "confirm-dialog-confirm-btn"}
            onClick={onConfirm}
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
