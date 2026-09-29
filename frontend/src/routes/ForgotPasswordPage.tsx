import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { Mail } from "lucide-react";
import * as authApi from "../api/auth";
import { copy } from "../i18n/copy";
import { useLang } from "../i18n/useLang";
import "./AuthPage.css";

export function ForgotPasswordPage() {
  const { lang, setLang } = useLang();
  const t = copy[lang];

  const [email, setEmail] = useState("");
  const [touched, setTouched] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  // The backend always responds success regardless of whether the email matched a real
  // account (see auth_service.request_password_reset's own docstring) — so this only ever
  // reflects "the request went through", never "that email exists".
  const [submitted, setSubmitted] = useState(false);

  const emailError = touched && !email ? t.fieldRequired : null;

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setTouched(true);
    if (!email) return;

    setIsSubmitting(true);
    try {
      await authApi.forgotPassword(email);
      setSubmitted(true);
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
        <h1>{t.forgotPasswordHeading}</h1>
        <p className="auth-subtitle">{t.forgotPasswordSubtitle}</p>

        {submitted ? (
          <p className="auth-alert-success" role="status">
            {t.resetLinkSentMessage}
          </p>
        ) : (
          <form className="auth-form" onSubmit={handleSubmit} noValidate>
            <div className="auth-field-group">
              <label htmlFor="forgot-email">{t.emailLabel}</label>
              <div className={`auth-input-wrap ${emailError ? "has-error" : ""}`}>
                <Mail />
                <input
                  id="forgot-email"
                  type="email"
                  placeholder={t.emailPlaceholder}
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  onBlur={() => setTouched(true)}
                />
              </div>
              {emailError && <p className="auth-field-error">{emailError}</p>}
            </div>

            <button type="submit" className="auth-submit" disabled={isSubmitting}>
              {isSubmitting ? t.sendingResetLink : t.sendResetLink}
            </button>
          </form>
        )}

        <p className="auth-switch">
          <Link to="/login" className="auth-link">
            {t.backToLogin}
          </Link>
        </p>
      </div>
    </main>
  );
}
