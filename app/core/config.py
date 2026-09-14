from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    DATABASE_URL: str
    SECRET_KEY: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    STORAGE_ROOT: str = "storage"
    # Comma-separated allow-list, not a regex — kept as an explicit list deliberately (see
    # main.py). Defaults preserve exactly the current hardcoded local-dev origins; a deployed
    # environment (e.g. Render) sets this env var instead of needing a code change per origin.
    CORS_ORIGINS: str = "http://localhost:5173,http://localhost:5174"

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]


settings = Settings()
