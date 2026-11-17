"""Users, roles, teams, authorized email recipients."""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
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

    role: Mapped[Role] = relationship(lazy="joined")
    team: Mapped[Team | None] = relationship(back_populates="members", foreign_keys=[team_id])

    @property
    def role_name(self) -> RoleName:
        return self.role.name


class AuthorizedRecipient(TimestampMixin, Base):
    """Management email addresses allowed to receive reports. Configured by admins only."""
    __tablename__ = "authorized_recipients"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    purpose: Mapped[str] = mapped_column(String(40), default="eod_report", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
