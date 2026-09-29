import { useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { Eye, EyeOff, Lock } from "lucide-react";
import * as authApi from "../api/auth";
import { ApiError } from "../api/client";
import { copy } from "../i18n/copy";
import { useLang } from "../i18n/useLang";
import "./AuthPage.css";

const MIN_PASSWORD_LENGTH = 8;

export function ResetPasswordPage() {
  const { lang, setLang } = useLang();
  const t = copy[lang];
  const [searchParams] = useSearchParams();
  const token = searchParams.get("token");

  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [touched, setTouched] = useState<{ password?: boolean; confirmPassword?: boolean }>({});
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [succeeded, setSucceeded] = useState(false);

  const passwordError =
    touched.password && !password
      ? t.fieldRequired
      : touched.password && password.length < MIN_PASSWORD_LENGTH
        ? t.passwordTooShort(MIN_PASSWORD_LENGTH)
        : null;
  const confirmPasswordError =
    touched.confirmPassword && !confirmPassword
      ? t.fieldRequired
      : touched.confirmPassword && confirmPassword !== password
        ? t.passwordMismatch
        : null;

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setTouched({ password: true, confirmPassword: true });
    if (!token || !password || password.length < MIN_PASSWORD_LENGTH || confirmPassword !== password) return;

    setError(null);
    setIsSubmitting(true);
    try {
      await authApi.resetPassword(token, password);
      setSucceeded(true);
    } catch (err) {
      setError(err instanceof ApiError ? String(err.detail) : t.resetPasswordFailed);
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <main className="auth-page">
      <div className="auth-decor auth-decor-tl" />
      <div className="auth-decor auth-decor-br" />

      <div className="auth-lang-toggle">
        <button type="button" className={lang === "fr" ? "active" : ""} onClick={() => setLang("fr")}>
          FR
        </button>
        <button type="button" className={lang === "en" ? "active" : ""} onClick={() => setLang("en")}>
          EN
        </button>
      </div>

      <div className="auth-card">
        <div className="auth-logo">
          <img src="/antic_logo.png" alt="ANTIC" />
        </div>
        <h1>{t.resetPasswordHeading}</h1>
        <p className="auth-subtitle">{t.resetPasswordSubtitle}</p>

        {!token ? (
          <>
            <p className="auth-alert" role="alert">
              {t.resetPasswordMissingToken}
            </p>
            <p className="auth-switch">
              <Link to="/forgot-password" className="auth-link">
                {t.requestNewResetLink}
              </Link>
            </p>
          </>
        ) : succeeded ? (
          <>
            <p className="auth-alert-success" role="status">
              {t.resetPasswordSuccessMessage}
            </p>
            <p className="auth-switch">
              <Link to="/login" className="auth-link">
                {t.logIn}
              </Link>
            </p>
          </>
        ) : (
          <>
            <form className="auth-form" onSubmit={handleSubmit} noValidate>
              <div className="auth-field-group">
                <label htmlFor="reset-password">{t.newPasswordLabel}</label>
                <div className={`auth-input-wrap with-toggle ${passwordError ? "has-error" : ""}`}>
                  <Lock />
                  <input
                    id="reset-password"
                    type={showPassword ? "text" : "password"}
                    placeholder={t.registerPasswordPlaceholder(MIN_PASSWORD_LENGTH)}
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    onBlur={() => setTouched((prev) => ({ ...prev, password: true }))}
                  />
                  <button
                    type="button"
                    className="auth-field-toggle"
                    onClick={() => setShowPassword((v) => !v)}
                    aria-label={showPassword ? "Hide password" : "Show password"}
                  >
                    {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
                  </button>
                </div>
                {passwordError && <p className="auth-field-error">{passwordError}</p>}
              </div>

              <div className="auth-field-group">
                <label htmlFor="reset-confirm-password">{t.confirmPasswordLabel}</label>
                <div className={`auth-input-wrap with-toggle ${confirmPasswordError ? "has-error" : ""}`}>
                  <Lock />
                  <input
                    id="reset-confirm-password"
                    type={showPassword ? "text" : "password"}
                    placeholder={t.confirmPasswordPlaceholder}
                    value={confirmPassword}
                    onChange={(e) => setConfirmPassword(e.target.value)}
                    onBlur={() => setTouched((prev) => ({ ...prev, confirmPassword: true }))}
                  />
                </div>
                {confirmPasswordError && <p className="auth-field-error">{confirmPasswordError}</p>}
              </div>

              {error && (
                <p className="auth-alert" role="alert">
                  {error}
                </p>
              )}

              <button type="submit" className="auth-submit" disabled={isSubmitting}>
                {isSubmitting ? t.resettingPassword : t.resetPassword}
              </button>
            </form>

            <p className="auth-switch">
              <Link to="/login" className="auth-link">
                {t.backToLogin}
              </Link>
            </p>
          </>
        )}
      </div>
    </main>
  );
}
