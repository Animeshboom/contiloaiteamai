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
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

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
    login_rate_limit: str = "10/minute"

    # AI (Claude)
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-opus-5-5"

    # Email
    email_provider: str = "mock"  # mock | gmail_mcp
    email_sender: str = "studiotrack@localhost"
    gmail_credentials_file: str | None = None  # OAuth client secret json
    gmail_token_file: str | None = None  # stored user token json

    @field_validator("cors_origins", "allowed_upload_extensions", mode="before")
    @classmethod
    def _split_csv(cls, v):
        if isinstance(v, str) and not v.strip().startswith("["):
            return [s.strip() for s in v.split(",") if s.strip()]
        return v

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.studio_timezone)

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
