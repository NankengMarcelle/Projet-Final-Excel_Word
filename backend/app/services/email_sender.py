import smtplib
from email.message import EmailMessage

from app.core.config import settings


class EmailSender:
    def send_password_reset(self, *, to_email: str, reset_url: str) -> None:
        raise NotImplementedError


class ConsoleEmailSender(EmailSender):
    """Prints the reset link instead of sending real email. get_email_sender() below picks this
    whenever SMTP_HOST isn't configured — the default, out-of-the-box state — so the whole
    password-reset flow is testable end to end without any mail provider or credentials.

    Deliberately print(), not logger.info(): this app never calls logging.basicConfig or
    otherwise attaches a handler to the root logger (confirmed live — a logger.info() call here
    produced nothing in the uvicorn console, since Python's logging module is silent below
    WARNING with no handler configured), and the one job this class has is to be visible to
    whoever's running the dev server. A plain print reaches the console unconditionally,
    independent of whatever logging setup does or doesn't exist."""

    def send_password_reset(self, *, to_email: str, reset_url: str) -> None:
        print(f"[password reset] link for {to_email}: {reset_url}", flush=True)


class SmtpEmailSender(EmailSender):
    """Sends real email via Python's stdlib smtplib — works with any provider that exposes a
    standard SMTP interface (Gmail with an app password, SendGrid, AWS SES, Mailgun, etc.), so
    no provider-specific SDK is needed. Activated by get_email_sender() the moment SMTP_HOST is
    set; see config.py for the full set of SMTP_* settings this reads."""

    def send_password_reset(self, *, to_email: str, reset_url: str) -> None:
        message = EmailMessage()
        message["Subject"] = "Reset your SheetFlow password"
        message["From"] = settings.SMTP_FROM_EMAIL or settings.SMTP_USERNAME
        message["To"] = to_email
        message.set_content(
            "A password reset was requested for this account.\n\n"
            f"Reset your password: {reset_url}\n\n"
            "This link expires shortly. If you didn't request this, you can safely ignore "
            "this email — your password will not be changed."
        )
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
            if settings.SMTP_USE_TLS:
                server.starttls()
            if settings.SMTP_USERNAME and settings.SMTP_PASSWORD:
                server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
            server.send_message(message)


def get_email_sender() -> EmailSender:
    if settings.SMTP_HOST:
        return SmtpEmailSender()
    return ConsoleEmailSender()
