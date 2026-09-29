from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    DATABASE_URL: str
    SECRET_KEY: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30
    PASSWORD_RESET_TOKEN_EXPIRE_MINUTES: int = 30
    # Base URL of the deployed frontend, used to build the link inside a password-reset email
    # (the backend has no other way to know where the frontend is served from).
    FRONTEND_BASE_URL: str = "http://localhost:5173"
    # Left unset by default, which is deliberate: get_email_sender() (see email_sender.py) uses
    # that to decide between actually sending mail (SmtpEmailSender) and just logging the reset
    # link (ConsoleEmailSender) — so the password-reset flow works out of the box in dev/local
    # without needing a real mail account, and a deployment only needs to set these env vars to
    # start sending real email, no code change required.
    SMTP_HOST: str | None = None
    SMTP_PORT: int = 587
    SMTP_USERNAME: str | None = None
    SMTP_PASSWORD: str | None = None
    SMTP_FROM_EMAIL: str | None = None
    SMTP_USE_TLS: bool = True
    # Local disk is always used as a working directory (openpyxl/python-docx need a real file
    # path); STORAGE_ROOT is where that lives. When STORAGE_BACKEND is "s3", that local copy is
    # just a warm cache — object_storage.py mirrors every write to the S3-compatible bucket
    # below and excel_io.py downloads on a cache miss (see excel_io.py's module notes).
    STORAGE_ROOT: str = "storage"
    STORAGE_BACKEND: str = "local"  # "local" or "s3"
    S3_ENDPOINT_URL: str | None = None
    S3_REGION: str | None = None
    S3_BUCKET_NAME: str | None = None
    S3_ACCESS_KEY_ID: str | None = None
    S3_SECRET_ACCESS_KEY: str | None = None
    # Comma-separated allow-list, not a regex — kept as an explicit list deliberately (see
    # main.py). Defaults preserve exactly the current hardcoded local-dev origins; a deployed
    # environment (e.g. Render) sets this env var instead of needing a code change per origin.
    CORS_ORIGINS: str = "http://localhost:5173,http://localhost:5174"

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]


settings = Settings()
