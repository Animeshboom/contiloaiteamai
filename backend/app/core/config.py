"""Application settings, loaded from environment variables / .env file."""
from datetime import date
from functools import lru_cache
from zoneinfo import ZoneInfo

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", "../.env"), extra="ignore")

    app_name: str = "Contiloe StudioTrack AI"
    environment: str = "development"  # development | test | production
    debug: bool = False

    database_url: str = "postgresql+psycopg://studiotrack:studiotrack@localhost:5434/studiotrack"

    # Auth
    jwt_secret_key: str = Field(default="dev-insecure-change-me-please-32bytes!!", min_length=32)
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 8  # one working shift
    bcrypt_rounds: int = 12

    # Sign-in provider
    # local:    email/Employee ID + password checked by this API (tests, offline development)
    # supabase: Supabase Auth issues the tokens; this API verifies them and manages accounts
    auth_provider: str = "local"
    supabase_url: str | None = None  # https://<project>.supabase.co
    supabase_publishable_key: str | None = None  # public key; used to verify a password on change
    supabase_service_role_key: str | None = None  # SECRET: creates/updates logins. Server only
    supabase_jwt_secret: str | None = None  # only for legacy HS256 projects; otherwise JWKS is used
    # People without an email sign in with an Employee ID (e.g. EMP001), stored as emp001@<domain>.
    # Must look like a real domain (email validators reject .local/.test).
    login_id_email_domain: str = "staff.studiotrack.app"
    staff_checkin_cutoff_hour: int = 12  # not checked in by this hour (studio time) shows as Absent; late check-in works
    show_checkin_times: bool = False  # times are always saved; set true to show check-in/out times in the app
    low_attendance_pct: int = 75
    chat_retention_days: int = 90  # chat messages older than this are deleted automatically  # people below this month's attendance % are flagged for leads and admins

    # CORS
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]  # env: JSON array

    # Studio
    studio_timezone: str = "Asia/Kolkata"
    eod_deadline_hour: int = 19  # default "end of day" deadline, local studio time
    half_day_max_hours: float = 4.5  # shorter shifts are auto-marked Half Day at check-out
    max_shift_hours: float = 16  # check-out allowed this long after check-in (night shifts); then auto-closed
    work_days: list[int] = [0, 1, 2, 3, 4, 5]  # Mon=0 … Sun=6; env: JSON array. Other days aren't counted absent
    holidays: list[date] = []  # env: JSON array of "YYYY-MM-DD"; not counted absent

    # Uploads
    upload_dir: str = "uploads"
    max_upload_mb: int = 25
    allowed_upload_extensions: list[str] = [
        ".png", ".jpg", ".jpeg", ".webp", ".gif", ".mp4", ".mov", ".webm",
        ".pdf", ".txt", ".zip", ".json", ".wav", ".mp3",
    ]

    # Rate limits and account protection
    login_rate_limit: str = "10/minute"
    login_max_attempts: int = 5  # wrong passwords in a row before the account is locked
    login_lock_minutes: int = 15
    admin_mfa_required: bool = True  # admins must use two-step login (authenticator app code)

    # AI (Claude)
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-opus-5-5"

    # Email / notifications
    # Off: notifications are in-app only and no email is queued. Turn on once Gmail is set up.
    email_enabled: bool = False
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
        if self.email_enabled:
            if self.email_provider != "mcp":
                problems.append("EMAIL_PROVIDER must be 'mcp' in production")
            if self.gmail_backend != "gmail":
                problems.append("GMAIL_BACKEND must be 'gmail' in production (mock only writes .eml files)")
            if "localhost" in self.app_base_url or "127.0.0.1" in self.app_base_url:
                problems.append("APP_BASE_URL must be the public URL of the web app (used in email links)")
        if self.auth_provider not in ("local", "supabase"):
            problems.append("AUTH_PROVIDER must be 'local' or 'supabase'")
        if self.auth_provider == "supabase":
            for name in ("supabase_url", "supabase_publishable_key", "supabase_service_role_key"):
                if not getattr(self, name):
                    problems.append(f"{name.upper()} is required when AUTH_PROVIDER=supabase")
        return problems

    @property
    def uses_supabase(self) -> bool:
        return self.auth_provider == "supabase"

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
