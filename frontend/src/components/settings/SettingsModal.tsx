import { CloseIcon, GlobeIcon, MonitorIcon, MoonIcon, SunIcon } from "../icons/SettingsIcons";
import { useTheme } from "../../theme/useTheme";
import type { ThemePreference } from "../../theme/ThemeContext";
import { useLang } from "../../i18n/useLang";
import type { Lang } from "../../i18n/LangContext";
import "./SettingsModal.css";

const THEME_OPTIONS: { value: ThemePreference; label: string; Icon: typeof SunIcon }[] = [
  { value: "light", label: "Light", Icon: SunIcon },
  { value: "dark", label: "Dark", Icon: MoonIcon },
  { value: "system", label: "System", Icon: MonitorIcon },
];

const LANG_OPTIONS: { value: Lang; label: string }[] = [
  { value: "fr", label: "Français" },
  { value: "en", label: "English" },
];

export function SettingsModal({ onClose }: { onClose: () => void }) {
  const { theme, setTheme } = useTheme();
  // This used to be a disabled, permanently-English dropdown with a "French — coming soon"
  // note — dead UI left over from before the real FR/EN toggle (the one in the header) existed.
  // Wired to the same shared `useLang()` state as everything else now, not a second, separate
  // preference: toggling here and toggling in the header are the exact same action.
  const { lang, setLang } = useLang();

  return (
    <div className="settings-overlay" onClick={onClose}>
      <div role="dialog" aria-label="Settings" className="settings-card" onClick={(e) => e.stopPropagation()}>
        <div className="settings-header">
          <h2>Settings</h2>
          <button type="button" className="settings-close-btn" onClick={onClose} aria-label="Close settings">
            <CloseIcon />
          </button>
        </div>

        <div className="settings-section">
          <h3>Appearance</h3>
          <div className="settings-theme-options" role="radiogroup" aria-label="Theme">
            {THEME_OPTIONS.map(({ value, label, Icon }) => (
              <button
                key={value}
                type="button"
                role="radio"
                aria-checked={theme === value}
                className={`settings-theme-btn ${theme === value ? "active" : ""}`}
                onClick={() => setTheme(value)}
              >
                <Icon />
                {label}
              </button>
            ))}
          </div>
        </div>

        <div className="settings-section">
          <h3>Language</h3>
          <div className="settings-language-row">
            <GlobeIcon />
            <div className="settings-lang-options" role="radiogroup" aria-label="Language">
              {LANG_OPTIONS.map(({ value, label }) => (
                <button
                  key={value}
                  type="button"
                  role="radio"
                  aria-checked={lang === value}
                  className={`settings-lang-btn ${lang === value ? "active" : ""}`}
                  onClick={() => setLang(value)}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
