import type { SaveStatus } from "../../hooks/useDebouncedAutosave";
import { AlertCircleIcon, CheckCircleIcon, SpinnerIcon } from "../icons/EditorIcons";
import { copy } from "../../i18n/copy";
import { useLang } from "../../i18n/useLang";

export function SaveStatusIndicator({ status }: { status: SaveStatus }) {
  const { lang } = useLang();
  const t = copy[lang];
  if (status === "idle") return null;
  const labels: Record<SaveStatus, string> = {
    idle: "",
    saving: t.savingStatus,
    saved: t.savedStatus,
    error: t.saveFailedStatus,
  };
  return (
    <span className={`save-status save-status-${status}`} role={status === "error" ? "alert" : undefined}>
      {status === "saving" && <SpinnerIcon className="save-status-spinner" />}
      {status === "saved" && <CheckCircleIcon />}
      {status === "error" && <AlertCircleIcon />}
      {labels[status]}
    </span>
  );
}
