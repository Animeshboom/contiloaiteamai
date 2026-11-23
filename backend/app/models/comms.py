"""Notifications, email logs, daily reports, audit logs."""
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.timeutils import utcnow
from app.models.base import UTCDateTime, JSONType, TimestampMixin, str_enum
from app.models.enums import EmailStatus, ReportStatus
from app.models.org import User


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (Index("ix_notifications_user_unread", "user_id", "read_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(60), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    link: Mapped[str | None] = mapped_column(String(255))
    entity_type: Mapped[str | None] = mapped_column(String(60))
    entity_id: Mapped[int | None] = mapped_column(Integer)
    # Idempotency: the same event for the same user is never stored twice.
    dedupe_key: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    read_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, nullable=False)


class EmailLog(TimestampMixin, Base):
    __tablename__ = "email_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    idempotency_key: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    tool_name: Mapped[str] = mapped_column(String(80), nullable=False)
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    recipients: Mapped[list] = mapped_column(JSONType, default=list, nullable=False)
    subject: Mapped[str] = mapped_column(String(300), nullable=False)
    body_preview: Mapped[str | None] = mapped_column(Text)
    status: Mapped[EmailStatus] = mapped_column(str_enum(EmailStatus, "email_status"), nullable=False, index=True)
    provider_message_id: Mapped[str | None] = mapped_column(String(200))
    error: Mapped[str | None] = mapped_column(Text)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    entity_type: Mapped[str | None] = mapped_column(String(60))
    entity_id: Mapped[int | None] = mapped_column(Integer)
    triggered_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    # Outbox fields: the exact MCP tool arguments, and retry scheduling.
    payload: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)
    next_attempt_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), index=True)
    last_attempt_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    sent_at: Mapped[datetime | None] = mapped_column(UTCDateTime())


class DailyReport(TimestampMixin, Base):
    __tablename__ = "daily_reports"
    __table_args__ = (Index("ix_daily_reports_date_status", "report_date", "status"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    report_date: Mapped[date] = mapped_column(Date, nullable=False)
    team_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id"))
    filters: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)
    metrics: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)  # deterministic snapshot
    ai_summary: Mapped[str | None] = mapped_column(Text)  # AI narrative, as generated
    ai_generated: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Structured narrative {summary, highlights[], concerns[]} and how it was produced:
    # ai_status: generated | template | rejected_unverified_numbers | ai_error | refused
    narrative: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)
    ai_status: Mapped[str | None] = mapped_column(String(40))
    ai_note: Mapped[str | None] = mapped_column(Text)
    subject: Mapped[str] = mapped_column(String(300), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)  # final, team-lead-editable email body
    status: Mapped[ReportStatus] = mapped_column(
        str_enum(ReportStatus, "report_status"), default=ReportStatus.DRAFT, nullable=False
    )
    recipients: Mapped[list] = mapped_column(JSONType, default=list, nullable=False)
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    approved_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    approved_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    # HMAC issued at approval over (report, approver, time, exact recipients); verified by the MCP server.
    approval_token: Mapped[str | None] = mapped_column(String(64))
    sent_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    sent_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    delivery_status: Mapped[str | None] = mapped_column(String(40))
    gmail_message_id: Mapped[str | None] = mapped_column(String(200))
    gmail_draft_id: Mapped[str | None] = mapped_column(String(200))
    # In-app reporting to the admin (works with email off): the lead adds issues and sends it.
    auto_generated: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    issues: Mapped[str | None] = mapped_column(Text)
    # Team lead's additions: {blockers, tomorrow_plan, artist_remarks: {name: text}, links: [{label, url}]}
    lead_input: Mapped[dict | None] = mapped_column(JSONType)
    submitted_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    submitted_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    admin_comment: Mapped[str | None] = mapped_column(Text)
    admin_commented_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    admin_commented_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))

    created_by: Mapped[User] = relationship(foreign_keys=[created_by_id])
    sent_by: Mapped[User | None] = relationship(foreign_keys=[sent_by_id])


class ChatMessage(Base):
    """A chat message in a group channel ("everyone", "leads" or "team:<id>"). Kept CHAT_RETENTION_DAYS."""
    __tablename__ = "chat_messages"
    __table_args__ = (Index("ix_chat_messages_channel_id", "channel", "id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    channel: Mapped[str] = mapped_column(String(40), nullable=False)
    sender_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, nullable=False, index=True)
    edited_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    deleted_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    deleted_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))


class ChatRead(Base):
    """How far each person has read in each chat (for unread counts)."""
    __tablename__ = "chat_reads"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    channel: Mapped[str] = mapped_column(String(40), primary_key=True)
    last_read_id: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (Index("ix_audit_entity", "entity_type", "entity_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    action: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(60), nullable=False)
    entity_id: Mapped[int | None] = mapped_column(Integer)
    before: Mapped[dict | None] = mapped_column(JSONType)
    after: Mapped[dict | None] = mapped_column(JSONType)
    ip_address: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, nullable=False, index=True)
