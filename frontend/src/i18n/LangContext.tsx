import { createContext, useEffect, useState, type ReactNode } from "react";

export type Lang = "fr" | "en";

const STORAGE_KEY = "antic_lang";

function readStoredLang(): Lang {
  return localStorage.getItem(STORAGE_KEY) === "en" ? "en" : "fr";
}

interface LangContextValue {
  lang: Lang;
  setLang: (lang: Lang) => void;
}

export const LangContext = createContext<LangContextValue | undefined>(undefined);

// App-wide, not just the auth pages (it started there — see authCopy.ts — but the same
// preference needs to hold once you're past login too, for the sidebar/header). Same
// localStorage key ANTIC's own UI prototype uses, so a preference set on either persists
// consistently for the same person.
export function LangProvider({ children }: { children: ReactNode }) {
  const [lang, setLang] = useState<Lang>(readStoredLang);

  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, lang);
  }, [lang]);

  return <LangContext.Provider value={{ lang, setLang }}>{children}</LangContext.Provider>;
}
