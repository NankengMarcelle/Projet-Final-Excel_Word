import { useCallback, useState } from "react";
import { fetchBlob } from "../api/client";

function triggerBrowserDownload(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}

export function useFileDownload() {
  const [isDownloading, setIsDownloading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const download = useCallback(async (path: string, fallbackFilename: string) => {
    setIsDownloading(true);
    setError(null);
    try {
      const { blob, filename } = await fetchBlob(path);
      triggerBrowserDownload(blob, filename ?? fallbackFilename);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Download failed");
      throw err;
    } finally {
      setIsDownloading(false);
    }
  }, []);

  return { download, isDownloading, error };
}
