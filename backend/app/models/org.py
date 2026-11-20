"""Users, roles, teams, authorized email recipients."""
from datetime import date as date_
from datetime import datetime

from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, Integer, String, Table, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.timeutils import utcnow
from app.models.base import UTCDateTime, SoftDeleteMixin, TimestampMixin, str_enum
from app.models.enums import RoleName


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[RoleName] = mapped_column(str_enum(RoleName, "role_name"), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(String(255))


class Team(TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "teams"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    department: Mapped[str | None] = mapped_column(String(120))
    description: Mapped[str | None] = mapped_column(Text)
    lead_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL", use_alter=True, name="fk_teams_lead_id_users"), index=True
    )

    lead: Mapped["User | None"] = relationship(foreign_keys=[lead_id], post_update=True)
    members: Mapped[list["User"]] = relationship(back_populates="team", foreign_keys="User.team_id")


class User(TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(160), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id"), nullable=False, index=True)
    team_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id", ondelete="SET NULL"), index=True)
    job_title: Mapped[str | None] = mapped_column(String(120))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Bumped on password change / deactivation / role change to invalidate outstanding JWTs.
    token_version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    # Supabase Auth user id (UUID) when AUTH_PROVIDER=supabase.
    auth_user_id: Mapped[str | None] = mapped_column(String(64), unique=True, index=True)
    # Optional sign-in ID for people without an email (e.g. EMP001); their login email is
    # <id>@LOGIN_ID_EMAIL_DOMAIN. People with a real email sign in with that instead.
    employee_code: Mapped[str | None] = mapped_column(String(40), unique=True, index=True)
    phone: Mapped[str | None] = mapped_column(String(32))
    # Artists may be signed in on one device: the latest Supabase session wins (see deps).
    active_session_id: Mapped[str | None] = mapped_column(String(64))
    active_session_at: Mapped[int | None] = mapped_column(Integer)  # sign-in time (unix seconds)
    # Lockout after repeated wrong passwords (local sign-in).
    failed_logins: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    locked_until: Mapped[datetime | None] = mapped_column(UTCDateTime())
    # Admin two-step login (local sign-in): TOTP secret, encrypted with a key derived from JWT_SECRET_KEY.
    totp_secret: Mapped[str | None] = mapped_column(String(255))
    totp_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    role: Mapped[Role] = relationship(lazy="joined")
    team: Mapped[Team | None] = relationship(back_populates="members", foreign_keys=[team_id])

    @property
    def role_name(self) -> RoleName:
        return self.role.name


class KnownDevice(Base):
    """Browsers/networks an admin has signed in from; a new one triggers an alert."""
    __tablename__ = "known_devices"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    user_agent: Mapped[str | None] = mapped_column(String(300))
    ip: Mapped[str | None] = mapped_column(String(64))
    first_seen_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, nullable=False)


holiday_teams = Table(
    "holiday_teams", Base.metadata,
    Column("holiday_id", ForeignKey("holidays.id", ondelete="CASCADE"), primary_key=True),
    Column("team_id", ForeignKey("teams.id", ondelete="CASCADE"), primary_key=True),
)


class Holiday(TimestampMixin, Base):
    """A day off: for everyone, or only for the listed teams."""
    __tablename__ = "holidays"

    id: Mapped[int] = mapped_column(primary_key=True)
    day: Mapped[date_] = mapped_column(Date, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    applies_to_all: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    teams: Mapped[list[Team]] = relationship(secondary=holiday_teams, lazy="selectin")


announcement_teams = Table(
    "announcement_teams", Base.metadata,
    Column("announcement_id", ForeignKey("announcements.id", ondelete="CASCADE"), primary_key=True),
    Column("team_id", ForeignKey("teams.id", ondelete="CASCADE"), primary_key=True),
)


class Announcement(TimestampMixin, Base):
    """A message to artists: everyone, or chosen teams. Optional last day to show it."""
    __tablename__ = "announcements"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    author_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    applies_to_all: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    show_until: Mapped[date_ | None] = mapped_column(Date, index=True)

    author: Mapped["User | None"] = relationship(foreign_keys=[author_id])
    teams: Mapped[list[Team]] = relationship(secondary=announcement_teams, lazy="selectin")


class AuthorizedRecipient(TimestampMixin, Base):
    """Management email addresses allowed to receive reports. Configured by admins only."""
    __tablename__ = "authorized_recipients"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    purpose: Mapped[str] = mapped_column(String(40), default="eod_report", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
