import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Eye, EyeOff, Lock, Mail, User } from "lucide-react";
import { useAuth } from "../auth/useAuth";
import { ApiError } from "../api/client";
import { copy } from "../i18n/copy";
import { useLang } from "../i18n/useLang";
import "./AuthPage.css";

const MIN_PASSWORD_LENGTH = 8;

export function RegisterPage() {
  const { register } = useAuth();
  const navigate = useNavigate();
  const { lang, setLang } = useLang();
  const t = copy[lang];

  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [touched, setTouched] = useState<{
    fullName?: boolean;
    email?: boolean;
    password?: boolean;
    confirmPassword?: boolean;
  }>({});
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const fullNameError = touched.fullName && !fullName ? t.fieldRequired : null;
  const emailError = touched.email && !email ? t.fieldRequired : null;
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
    setTouched({ fullName: true, email: true, password: true, confirmPassword: true });
    if (
      !fullName ||
      !email ||
      !password ||
      password.length < MIN_PASSWORD_LENGTH ||
      confirmPassword !== password
    )
      return;

    setError(null);
    setIsSubmitting(true);
    try {
      await register(email, password, fullName);
      navigate("/workspace");
    } catch (err) {
      setError(err instanceof ApiError ? String(err.detail) : t.registerFailed);
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
        <h1>{t.registerHeading}</h1>
        <p className="auth-subtitle">{t.registerSubtitle}</p>

        <form className="auth-form" onSubmit={handleSubmit} noValidate>
          <div className="auth-field-group">
            <label htmlFor="register-name">{t.fullNameLabel}</label>
            <div className={`auth-input-wrap ${fullNameError ? "has-error" : ""}`}>
              <User />
              <input
                id="register-name"
                type="text"
                placeholder={t.fullNamePlaceholder}
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                onBlur={() => setTouched((prev) => ({ ...prev, fullName: true }))}
              />
            </div>
            {fullNameError && <p className="auth-field-error">{fullNameError}</p>}
          </div>

          <div className="auth-field-group">
            <label htmlFor="register-email">{t.emailLabel}</label>
            <div className={`auth-input-wrap ${emailError ? "has-error" : ""}`}>
              <Mail />
              <input
                id="register-email"
                type="email"
                placeholder={t.emailPlaceholder}
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                onBlur={() => setTouched((prev) => ({ ...prev, email: true }))}
              />
            </div>
            {emailError && <p className="auth-field-error">{emailError}</p>}
          </div>

          <div className="auth-field-group">
            <label htmlFor="register-password">{t.passwordLabel}</label>
            <div className={`auth-input-wrap with-toggle ${passwordError ? "has-error" : ""}`}>
              <Lock />
              <input
                id="register-password"
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
            <label htmlFor="register-confirm-password">{t.confirmPasswordLabel}</label>
            <div className={`auth-input-wrap with-toggle ${confirmPasswordError ? "has-error" : ""}`}>
              <Lock />
              <input
                id="register-confirm-password"
                type={showConfirmPassword ? "text" : "password"}
                placeholder={t.confirmPasswordPlaceholder}
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                onBlur={() => setTouched((prev) => ({ ...prev, confirmPassword: true }))}
              />
              <button
                type="button"
                className="auth-field-toggle"
                onClick={() => setShowConfirmPassword((v) => !v)}
                aria-label={showConfirmPassword ? "Hide password" : "Show password"}
              >
                {showConfirmPassword ? <EyeOff size={18} /> : <Eye size={18} />}
              </button>
            </div>
            {confirmPasswordError && <p className="auth-field-error">{confirmPasswordError}</p>}
          </div>

          {error && (
            <p className="auth-alert" role="alert">
              {error}
            </p>
          )}

          <button type="submit" className="auth-submit" disabled={isSubmitting}>
            {isSubmitting ? t.creatingAccount : t.createAccount}
          </button>
        </form>

        <p className="auth-switch">
          {t.haveAccount}{" "}
          <Link to="/login" className="auth-link">
            {t.logIn}
          </Link>
        </p>
      </div>
    </main>
  );
}
