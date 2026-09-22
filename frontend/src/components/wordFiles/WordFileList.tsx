import { useQuery } from "@tanstack/react-query";
import { listWordFiles } from "../../api/conversions";
import { WordFileRow } from "./WordFileRow";
import { LoadingState } from "../common/LoadingState";
import { copy } from "../../i18n/copy";
import { useLang } from "../../i18n/useLang";

export function WordFileList() {
  const { lang } = useLang();
  const t = copy[lang];

  const {
    data: files,
    isLoading,
    error,
  } = useQuery({
    queryKey: ["word-files"],
    queryFn: listWordFiles,
  });

  if (isLoading) return <LoadingState message={t.loadingWordFiles} />;
  if (error) return <p role="alert" className="word-files-status">{t.failedToLoadWordFiles}</p>;

  if (!files || files.length === 0) {
    return (
      <div className="word-files-empty">
        <p>{t.noWordFilesYet}</p>
      </div>
    );
  }

  return (
    <div className="word-file-table">
      <div className="word-file-columns">
        <span>{t.colName}</span>
        <span>{t.colSource}</span>
        <span>{t.colSize}</span>
        <span>{t.colConverted}</span>
        <span />
      </div>
      {files.map((file) => (
        <WordFileRow key={file.conversion_id} file={file} />
      ))}
    </div>
  );
}
