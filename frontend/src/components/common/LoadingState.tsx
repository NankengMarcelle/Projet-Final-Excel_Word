import { SpinnerIcon } from "../icons/EditorIcons";

// Shared full-page/section loading treatment — spinner + message, optionally with a real
// progress bar (used by the editor's worksheet load, which fetches sheets sequentially and can
// otherwise sit on a static message for 10-20s+ on a large workbook). Replaces every bare
// `<p>{message}</p>` loading state across the app with one consistent look.
export function LoadingState({
  message,
  progress,
}: {
  message: string;
  progress?: { current: number; total: number };
}) {
  const percent = progress && progress.total > 0 ? Math.min(100, (progress.current / progress.total) * 100) : null;

  return (
    <div className="loading-state" role="status">
      <div className="loading-state-message">
        <SpinnerIcon className="loading-spinner" />
        <span>
          {message}
          {progress ? ` (${progress.current}/${progress.total})` : ""}
        </span>
      </div>
      {percent !== null && (
        <div className="loading-progress-track">
          <div className="loading-progress-fill" style={{ width: `${percent}%` }} />
        </div>
      )}
    </div>
  );
}
