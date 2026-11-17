"""Shared column mixins and helpers."""
from datetime import datetime

from sqlalchemy import JSON, DateTime, Enum as SAEnum, TypeDecorator, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.timeutils import ensure_utc, utcnow


class UTCDateTime(TypeDecorator):
    """TIMESTAMPTZ that always round-trips as timezone-aware UTC (even on SQLite)."""
    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        return ensure_utc(value) if value is not None else None

    def process_result_value(self, value, dialect):
        return ensure_utc(value) if value is not None else None

# JSONB on Postgres, plain JSON elsewhere (tests use SQLite).
JSONType = JSON().with_variant(JSONB(), "postgresql")


def str_enum(enum_cls, name: str):
    """Store enums as VARCHAR + CHECK constraint (portable, migration-friendly)."""
    return SAEnum(
        enum_cls,
        name=name,
        native_enum=False,
        create_constraint=True,
        length=40,
        values_callable=lambda e: [m.value for m in e],
        validate_strings=True,
    )


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=utcnow, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=utcnow, onupdate=utcnow, server_default=func.now(), nullable=False
    )


class SoftDeleteMixin:
    deleted_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True, index=True)

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None
