import { WordFileList } from "../components/wordFiles/WordFileList";
import { copy } from "../i18n/copy";
import { useLang } from "../i18n/useLang";
import "./WordFilesPage.css";

export function WordFilesPage() {
  const { lang } = useLang();
  const t = copy[lang];

  return (
    <main className="word-files-main">
      <section className="word-files-heading-section">
        <h1 className="word-files-heading">{t.navWordFiles}</h1>
        <p className="word-files-subtitle">{t.wordFilesSubtitle}</p>
      </section>
      <section>
        <WordFileList />
      </section>
    </main>
  );
}
