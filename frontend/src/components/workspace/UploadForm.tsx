import { useRef, useState, type ChangeEvent, type DragEvent } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { importWorkbook } from "../../api/workbooks";
import { ApiError } from "../../api/client";
import { UploadCloudIcon } from "../icons/WorkspaceIcons";
import { SpinnerIcon } from "../icons/EditorIcons";
import { copy } from "../../i18n/copy";
import { useLang } from "../../i18n/useLang";

export function UploadForm() {
  const { lang } = useLang();
  const t = copy[lang];
  const queryClient = useQueryClient();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [error, setError] = useState<string | null>(null);
  const [isDragging, setIsDragging] = useState(false);

  const mutation = useMutation({
    mutationFn: importWorkbook,
    onSuccess: () => {
      setError(null);
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
      void queryClient.invalidateQueries({ queryKey: ["workbooks"] });
    },
    onError: (err) => {
      setError(err instanceof ApiError ? String(err.detail) : t.uploadFailed);
    },
  });

  function uploadFile(file: File | undefined) {
    if (!file) return;
    mutation.mutate(file);
  }

  function handleFileChange(event: ChangeEvent<HTMLInputElement>) {
    uploadFile(event.target.files?.[0]);
  }

  function handleDrop(event: DragEvent<HTMLButtonElement>) {
    event.preventDefault();
    setIsDragging(false);
    uploadFile(event.dataTransfer.files?.[0]);
  }

  return (
    <div className="upload-card">
      <button
        type="button"
        className={`upload-card-preview ${isDragging ? "dragging" : ""}`}
        onClick={() => fileInputRef.current?.click()}
        onDragOver={(event) => {
          event.preventDefault();
          setIsDragging(true);
        }}
        onDragLeave={() => setIsDragging(false)}
        onDrop={handleDrop}
        disabled={mutation.isPending}
      >
        {mutation.isPending ? <SpinnerIcon className="btn-spinner" /> : <UploadCloudIcon />}
        <span className="upload-card-label">
          {mutation.isPending ? t.uploading : t.uploadWorkbookLabel}
        </span>
      </button>
      <input
        ref={fileInputRef}
        type="file"
        accept=".xlsx"
        onChange={handleFileChange}
        disabled={mutation.isPending}
      />
      {error && (
        <p role="alert" className="upload-card-error">
          {error}
        </p>
      )}
    </div>
  );
}
