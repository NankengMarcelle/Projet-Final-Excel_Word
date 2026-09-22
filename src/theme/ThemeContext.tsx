import { createContext, useCallback, useEffect, useState, type ReactNode } from "react";

export type ThemePreference = "light" | "dark" | "system";

const THEME_STORAGE_KEY = "sheetflow_theme";

interface ThemeContextValue {
  theme: ThemePreference;
  setTheme: (theme: ThemePreference) => void;
}

export const ThemeContext = createContext<ThemeContextValue | undefined>(undefined);

function applyTheme(theme: ThemePreference): void {
  if (theme === "system") {
    document.documentElement.removeAttribute("data-theme");
  } else {
    document.documentElement.setAttribute("data-theme", theme);
  }
}

function readStoredTheme(): ThemePreference {
  const stored = localStorage.getItem(THEME_STORAGE_KEY);
  // Default to light for anyone who hasn't explicitly picked a theme yet (via Settings), rather
  // than following the OS's prefers-color-scheme — "system" (which never itself gets persisted,
  // see setTheme below) is still a real, selectable option, just no longer the implicit starting
  // point for a first-time visitor.
  return stored === "light" || stored === "dark" ? stored : "light";
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<ThemePreference>(readStoredTheme);

  // Applied on mount too (not just on change) so a stored preference from a previous visit
  // takes effect immediately, before anything renders with the wrong palette.
  useEffect(() => {
    applyTheme(theme);
  }, [theme]);

  const setTheme = useCallback((next: ThemePreference) => {
    setThemeState(next);
    if (next === "system") {
      localStorage.removeItem(THEME_STORAGE_KEY);
    } else {
      localStorage.setItem(THEME_STORAGE_KEY, next);
    }
  }, []);

  return <ThemeContext.Provider value={{ theme, setTheme }}>{children}</ThemeContext.Provider>;
}
