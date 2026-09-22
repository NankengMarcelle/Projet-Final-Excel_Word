import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Eye, EyeOff, Lock, User } from "lucide-react";
import { useAuth } from "../auth/useAuth";
import { ApiError } from "../api/client";
import { copy } from "../i18n/copy";
import { useLang } from "../i18n/useLang";
import "./AuthPage.css";

export function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const { lang, setLang } = useLang();
  const t = copy[lang];

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [rememberMe, setRememberMe] = useState(true);
  const [showPassword, setShowPassword] = useState(false);
  const [touched, setTouched] = useState<{ email?: boolean; password?: boolean }>({});
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const emailError = touched.email && !email ? t.fieldRequired : null;
  const passwordError = touched.password && !password ? t.fieldRequired : null;

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setTouched({ email: true, password: true });
    if (!email || !password) return;

    setError(null);
    setIsSubmitting(true);
    try {
      await login(email, password, rememberMe);
      navigate("/workspace");
    } catch (err) {
      setError(err instanceof ApiError ? String(err.detail) : t.loginFailed);
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
        <h1>{t.loginHeading}</h1>
        <p className="auth-subtitle">{t.loginSubtitle}</p>

        <form className="auth-form" onSubmit={handleSubmit} noValidate>
          <div className="auth-field-group">
            <label htmlFor="login-email">{t.usernameLabel}</label>
            <div className={`auth-input-wrap ${emailError ? "has-error" : ""}`}>
              <User />
              <input
                id="login-email"
                type="email"
                placeholder={t.usernamePlaceholder}
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                onBlur={() => setTouched((prev) => ({ ...prev, email: true }))}
              />
            </div>
            {emailError && <p className="auth-field-error">{emailError}</p>}
          </div>

          <div className="auth-field-group">
            <label htmlFor="login-password">{t.passwordLabel}</label>
            <div className={`auth-input-wrap with-toggle ${passwordError ? "has-error" : ""}`}>
              <Lock />
              <input
                id="login-password"
                type={showPassword ? "text" : "password"}
                placeholder={t.passwordPlaceholder}
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

          <div className="auth-row">
            <label className="auth-checkbox">
              <input
                type="checkbox"
                checked={rememberMe}
                onChange={(e) => setRememberMe(e.target.checked)}
              />
              {t.keepLoggedIn}
            </label>
            {/* No password-reset flow exists on the backend yet; kept inert rather than faking one. */}
            <span className="auth-link-muted" aria-disabled="true">
              {t.forgotPassword}
            </span>
          </div>

          {error && (
            <p className="auth-alert" role="alert">
              {error}
            </p>
          )}

          <button type="submit" className="auth-submit" disabled={isSubmitting}>
            {isSubmitting ? t.loggingIn : t.logIn}
          </button>
        </form>

        <p className="auth-switch">
          {t.noAccount}{" "}
          <Link to="/register" className="auth-link">
            {t.signUp}
          </Link>
        </p>
      </div>
    </main>
  );
}
