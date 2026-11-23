"""Studio-wide settings an admin can change from the dashboard."""
from sqlalchemy import Boolean, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TimestampMixin


class AIProviderSetting(TimestampMixin, Base):
    """One row per AI provider. The API key is encrypted (never returned to the browser).

    At most one row is active; with no active row the app falls back to ANTHROPIC_API_KEY from the environment.
    """
    __tablename__ = "ai_providers"

    provider: Mapped[str] = mapped_column(String(20), primary_key=True)  # anthropic | openai | gemini | openrouter | custom
    api_key_enc: Mapped[str | None] = mapped_column(Text)
    key_hint: Mapped[str | None] = mapped_column(String(8))  # last 4 characters, for display only
    model: Mapped[str | None] = mapped_column(String(120))
    base_url: Mapped[str | None] = mapped_column(String(300))
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    updated_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
