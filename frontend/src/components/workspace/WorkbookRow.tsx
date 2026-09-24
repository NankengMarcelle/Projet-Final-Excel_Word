import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import type { WorkbookRead } from "../../types/workbook";
import { deleteWorkbook, renameWorkbook } from "../../api/workbooks";
import { useFileDownload } from "../../hooks/useFileDownload";
import { copy } from "../../i18n/copy";
import { useLang } from "../../i18n/useLang";
import type { Lang } from "../../i18n/LangContext";
import {
  DownloadIcon,
  KebabIcon,
  OpenIcon,
  PencilIcon,
  SpreadsheetFileIcon,
  TrashIcon,
} from "../icons/WorkspaceIcons";
import { SpinnerIcon } from "../icons/EditorIcons";

function formatBytes(bytes: number | null): string {
  if (bytes === null) return "—";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

// `undefined` locale (the browser's own) previously meant the date format never actually
// followed the FR/EN toggle — a French-toggled UI could still show "Sep 15, 2026" if the
// browser itself was set to English. Mapping the app's own lang to a concrete locale ties it to
// the same toggle as everything else on the page.
function localeFor(lang: Lang): string {
  return lang === "fr" ? "fr-FR" : "en-US";
}

// Day and time are shown separately now (two lines) instead of one-or-the-other depending on
// recency — the grouping header ("Aujourd'hui") already tells you a row is from today, but the
// row itself used to go silent on the actual date once it did, which meant checking exactly
// *when* today a file was touched (vs. just "today") always needed a second click into it.
function formatDay(iso: string, lang: Lang): string {
  return new Date(iso).toLocaleDateString(localeFor(lang), { month: "short", day: "numeric", year: "numeric" });
}

function formatTime(iso: string, lang: Lang): string {
  return new Date(iso).toLocaleTimeString(localeFor(lang), { hour: "numeric", minute: "2-digit" });
}

// A long real filename (this app's own test data routinely runs 60-90 characters) would
// otherwise depend entirely on the column's CSS ellipsis to stay readable — fine most of the
// time, but it means the row's rendered width is at the mercy of whatever the container happens
// to be, and a DOM inspection or a screen reader still gets the full, untruncated string. Trimming
// the actual text keeps every row's name predictable regardless of layout.
const MAX_NAME_LENGTH = 46;

function truncateName(name: string): string {
  return name.length > MAX_NAME_LENGTH ? `${name.slice(0, MAX_NAME_LENGTH - 1)}…` : name;
}

export function WorkbookRow({ workbook }: { workbook: WorkbookRead }) {
  const { lang } = useLang();
  const t = copy[lang];
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { download, isDownloading, error: downloadError } = useFileDownload();

  const [menuOpen, setMenuOpen] = useState(false);
  const [isRenaming, setIsRenaming] = useState(false);
  const [nameDraft, setNameDraft] = useState(workbook.filename);

  const menuRef = useRef<HTMLDivElement>(null);
  const renameInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!menuOpen) return;
    function handleClick(event: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        setMenuOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [menuOpen]);

  useEffect(() => {
    if (isRenaming) renameInputRef.current?.select();
  }, [isRenaming]);

  const deleteMutation = useMutation({
    mutationFn: () => deleteWorkbook(workbook.id),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["workbooks"] }),
  });

  const renameMutation = useMutation({
    mutationFn: (filename: string) => renameWorkbook(workbook.id, filename),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["workbooks"] }),
    onError: () => setNameDraft(workbook.filename),
  });

  function openWorkbook() {
    navigate(`/workbooks/${workbook.id}`);
  }

  function commitRename() {
    setIsRenaming(false);
    const trimmed = nameDraft.trim();
    if (trimmed && trimmed !== workbook.filename) {
      renameMutation.mutate(trimmed);
    } else {
      setNameDraft(workbook.filename);
    }
  }

  return (
    <div
      className="workbook-row"
      role="button"
      tabIndex={0}
      onClick={() => !isRenaming && openWorkbook()}
      onKeyDown={(event) => {
        if (event.key === "Enter" && !isRenaming) openWorkbook();
      }}
    >
      <div className="workbook-row-name">
        <SpreadsheetFileIcon />
        {isRenaming ? (
          <input
            ref={renameInputRef}
            className="workbook-rename-input"
            value={nameDraft}
            onClick={(event) => event.stopPropagation()}
            onChange={(event) => setNameDraft(event.target.value)}
            onBlur={commitRename}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                event.preventDefault();
                commitRename();
              }
              if (event.key === "Escape") {
                setNameDraft(workbook.filename);
                setIsRenaming(false);
              }
            }}
          />
        ) : (
          <span title={workbook.filename}>{truncateName(workbook.filename)}</span>
        )}
      </div>
      <span className="workbook-row-size">{formatBytes(workbook.file_size_bytes)}</span>
      <span className="workbook-row-date">{formatDay(workbook.created_at, lang)}</span>
      <span className="workbook-row-time">{formatTime(workbook.created_at, lang)}</span>

      <div ref={menuRef} style={{ position: "relative" }}>
        <button
          type="button"
          className={`workbook-row-menu-btn ${menuOpen ? "open" : ""}`}
          aria-label={t.workbookActions}
          onClick={(event) => {
            event.stopPropagation();
            setMenuOpen((open) => !open);
          }}
        >
          <KebabIcon />
        </button>
        {menuOpen && (
          <div className="workbook-row-menu" onClick={(event) => event.stopPropagation()}>
            <button
              type="button"
              onClick={() => {
                setMenuOpen(false);
                openWorkbook();
              }}
            >
              <OpenIcon /> {t.openAction}
            </button>
            <button
              type="button"
              onClick={() => {
                setMenuOpen(false);
                setIsRenaming(true);
              }}
            >
              <PencilIcon /> {t.renameAction}
            </button>
            <button
              type="button"
              disabled={isDownloading}
              onClick={() => {
                setMenuOpen(false);
                void download(`/workbooks/${workbook.id}/download`, workbook.filename);
              }}
            >
              {isDownloading ? <SpinnerIcon className="btn-spinner" /> : <DownloadIcon />}{" "}
              {isDownloading ? t.downloading : t.downloadAction}
            </button>
            <button
              type="button"
              className="danger"
              disabled={deleteMutation.isPending}
              onClick={() => {
                setMenuOpen(false);
                deleteMutation.mutate();
              }}
            >
              <TrashIcon /> {t.removeAction}
            </button>
          </div>
        )}
      </div>

      {downloadError && (
        <p role="alert" className="workbook-row-error">
          {downloadError}
        </p>
      )}
    </div>
  );
}
