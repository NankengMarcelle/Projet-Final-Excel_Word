import { FileText } from "lucide-react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import type { WordFileRead } from "../../types/conversion";
import { useFileDownload } from "../../hooks/useFileDownload";
import { deleteConversion } from "../../api/conversions";
import { DownloadIcon, TrashIcon } from "../icons/WorkspaceIcons";
import { SpinnerIcon } from "../icons/EditorIcons";
import { copy } from "../../i18n/copy";
import { useLang } from "../../i18n/useLang";
import type { Lang } from "../../i18n/LangContext";

function formatBytes(bytes: number | null): string {
  if (bytes === null) return "—";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

// Same locale-follows-the-FR/EN-toggle fix as WorkbookRow.tsx — see that file's own comment.
function localeFor(lang: Lang): string {
  return lang === "fr" ? "fr-FR" : "en-US";
}

function formatDate(iso: string, lang: Lang): string {
  const date = new Date(iso);
  const isToday = date.toDateString() === new Date().toDateString();
  const locale = localeFor(lang);
  return isToday
    ? date.toLocaleTimeString(locale, { hour: "numeric", minute: "2-digit" })
    : date.toLocaleDateString(locale, { month: "short", day: "numeric", year: "numeric" });
}

export function WordFileRow({ file }: { file: WordFileRead }) {
  const { lang } = useLang();
  const t = copy[lang];
  const queryClient = useQueryClient();
  const { download, isDownloading, error } = useFileDownload();

  const deleteMutation = useMutation({
    mutationFn: () => deleteConversion(file.conversion_id),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["word-files"] }),
  });

  async function handleDownload() {
    if (isDownloading) return;
    await download(`/conversions/${file.conversion_id}/download`, file.filename);
    // downloaded_at (shown as the "last downloaded" hint below) changes as a side effect of
    // streaming the file — refetch so that stays current after a repeat download.
    void queryClient.invalidateQueries({ queryKey: ["word-files"] });
  }

  return (
    <div
      className="word-file-row"
      role="button"
      tabIndex={0}
      onClick={handleDownload}
      onKeyDown={(event) => {
        if (event.key === "Enter") handleDownload();
      }}
    >
      <div className="word-file-row-name">
        <FileText size={20} />
        <span>{file.filename}</span>
      </div>
      <span className="word-file-row-source">
        {file.workbook_filename} — {file.worksheet_name}
      </span>
      <span className="word-file-row-size">{formatBytes(file.file_size_bytes)}</span>
      <span className="word-file-row-date">{formatDate(file.created_at, lang)}</span>
      <div className="word-file-row-action">
        <button
          type="button"
          disabled={isDownloading}
          onClick={(event) => {
            event.stopPropagation();
            void handleDownload();
          }}
        >
          {isDownloading ? <SpinnerIcon className="btn-spinner" /> : <DownloadIcon />}{" "}
          {isDownloading ? t.downloading : t.downloadAction}
        </button>
        <button
          type="button"
          className="word-file-row-delete"
          aria-label={t.removeAction}
          title={t.removeAction}
          disabled={deleteMutation.isPending}
          onClick={(event) => {
            event.stopPropagation();
            deleteMutation.mutate();
          }}
        >
          {deleteMutation.isPending ? <SpinnerIcon className="btn-spinner" /> : <TrashIcon />}
        </button>
      </div>

      {error && (
        <p role="alert" className="word-file-row-error">
          {error}
        </p>
      )}
      {deleteMutation.isError && (
        <p role="alert" className="word-file-row-error">
          {t.wordFileDeleteFailed}
        </p>
      )}
    </div>
  );
}
