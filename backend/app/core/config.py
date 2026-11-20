"""Application settings, loaded from environment variables / .env file."""
from functools import lru_cache
from zoneinfo import ZoneInfo

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", "../.env"), extra="ignore")

    app_name: str = "StudioTrack AI"
    environment: str = "development"  # development | test | production
    debug: bool = False

    database_url: str = "postgresql+psycopg://studiotrack:studiotrack@localhost:5434/studiotrack"

    # Auth
    jwt_secret_key: str = Field(default="dev-insecure-change-me-please-32bytes!!", min_length=32)
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 8  # one working shift
    bcrypt_rounds: int = 12

    # CORS
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]  # env: JSON array
    # Optional regex for extra origins, e.g. Cloudflare Pages preview builds:
    #   ^https://[a-z0-9-]+\.studiotrack-ai\.pages\.dev$     (unset = only CORS_ORIGINS are allowed)
    cors_origin_regex: str | None = None

    # Studio
    studio_timezone: str = "Asia/Kolkata"
    eod_deadline_hour: int = 19  # default "end of day" deadline, local studio time
    half_day_max_hours: float = 4.5  # shorter shifts are auto-marked Half Day at check-out

    # Uploads
    upload_dir: str = "uploads"
    max_upload_mb: int = 25
    allowed_upload_extensions: list[str] = [
        ".png", ".jpg", ".jpeg", ".webp", ".gif", ".mp4", ".mov", ".webm",
        ".pdf", ".txt", ".zip", ".json", ".wav", ".mp3",
    ]

    # Rate limits
    login_rate_limit: str = "10/minute"  # per client IP
    # Per account (independent of IP headers, which a client can forge behind some proxies)
    login_max_failures: int = 10
    login_failure_window_minutes: int = 15

    # AI (Claude)
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-opus-5-5"

    # Email / notifications
    # mcp:  deliver through the Gmail MCP server (the only provider for real use)
    # mock: in-process provider, used by the automated test suite only
    email_provider: str = "mcp"
    email_sender: str | None = None
    email_approval_secret: str = Field(default="dev-only-approval-secret-change-me-0123456789", min_length=32)
    gmail_mcp_url: str | None = None  # e.g. http://gmail-mcp:8765/mcp ; unset = spawn via stdio
    gmail_mcp_dir: str = "../mcp_servers"  # where the gmail_mcp package lives (stdio mode)
    gmail_backend: str = "gmail"  # passed to the MCP server: gmail (real) | mock (tests only)
    gmail_credentials_file: str | None = None  # OAuth client secret json (MCP server)
    gmail_token_file: str | None = None  # authorized user token json (MCP server)
    mail_outbox_dir: str = "mail_outbox"  # where mock deliveries are written as .eml
    app_base_url: str = "http://localhost:5173"  # links in emails
    email_max_attempts: int = 5
    deadline_reminder_hours: float = 2.0
    background_jobs: bool = True  # outbox dispatcher + deadline reminders

    @field_validator("cors_origins")
    @classmethod
    def _normalize_origins(cls, v: list[str]) -> list[str]:
        # Browsers send Origin as scheme://host[:port] with no trailing slash, and CORS matching is exact,
        # so "https://app.pages.dev/" would silently match nothing. Strip whitespace and trailing slashes only;
        # every other character (including "*") is kept, so production_problems() still rejects bad values.
        normalized = [o.strip().rstrip("/") for o in v]
        return [o for o in normalized if o]

    @field_validator("database_url")
    @classmethod
    def _psycopg_driver(cls, v: str) -> str:
        # Hosted Postgres (Render, Neon, Supabase, Railway) hands out postgres:// URLs.
        for prefix in ("postgres://", "postgresql://"):
            if v.startswith(prefix):
                return "postgresql+psycopg://" + v[len(prefix):]
        return v

    def production_problems(self) -> list[str]:
        """Configuration that is acceptable in development but unsafe in production."""
        problems = []
        weak = ("change-me", "dev-only", "dev-insecure", "test-")
        for name in ("jwt_secret_key", "email_approval_secret"):
            value = getattr(self, name)
            if len(value) < 32 or any(w in value for w in weak):
                problems.append(f"{name.upper()} must be a long random value (not a placeholder)")
        if self.database_url.endswith("studiotrack:studiotrack@localhost:5434/studiotrack"):
            problems.append("DATABASE_URL still points at the local development database")
        if self.email_provider != "mcp":
            problems.append("EMAIL_PROVIDER must be 'mcp' in production")
        if self.gmail_backend != "gmail":
            problems.append("GMAIL_BACKEND must be 'gmail' in production (mock only writes .eml files)")
        if "localhost" in self.app_base_url or "127.0.0.1" in self.app_base_url:
            problems.append("APP_BASE_URL must be the public URL of the web app (used in email links)")
        public_origins = [o for o in self.cors_origins if "localhost" not in o and "127.0.0.1" not in o]
        if "*" in self.cors_origins or not public_origins:
            problems.append('CORS_ORIGINS must be a JSON list of the web app URL(s), e.g. ["https://studiotrack-ai.pages.dev"]')
        return problems

    @property
    def email_configured(self) -> bool:
        """False until Gmail OAuth is set up. Emails then stay queued (pending) and go out once it is."""
        if self.email_provider == "mock" or self.gmail_backend == "mock" or self.gmail_mcp_url:
            return True
        return bool(self.gmail_credentials_file and self.gmail_token_file)

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.studio_timezone)

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
