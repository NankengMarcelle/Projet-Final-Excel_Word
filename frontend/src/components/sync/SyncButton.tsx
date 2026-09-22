import { SpinnerIcon } from "../icons/EditorIcons";

export function SyncButton({
  isSyncing,
  onSync,
}: {
  isSyncing: boolean;
  onSync: () => void;
}) {
  return (
    <button type="button" className="editor-action-btn small" onClick={onSync} disabled={isSyncing}>
      {isSyncing && <SpinnerIcon className="btn-spinner" />}
      {isSyncing ? "Synchronizing..." : "Synchronize"}
    </button>
  );
}
