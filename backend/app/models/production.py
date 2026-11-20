"""Projects, episodes, scenes."""
from datetime import date, datetime

from sqlalchemy import Column, Date, Float, ForeignKey, Integer, String, Table, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.timeutils import utcnow
from app.models.base import JSONType, SoftDeleteMixin, TimestampMixin, UTCDateTime, str_enum
from app.models.enums import ProjectStatus, ProjectType, WorkStatus


class Project(TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text)
    project_type: Mapped[ProjectType] = mapped_column(str_enum(ProjectType, "project_type"), nullable=False)
    status: Mapped[ProjectStatus] = mapped_column(
        str_enum(ProjectStatus, "project_status"), default=ProjectStatus.PLANNING, nullable=False, index=True
    )
    start_date: Mapped[date | None] = mapped_column(Date)
    expected_completion_date: Mapped[date | None] = mapped_column(Date)
    team_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id", ondelete="SET NULL"), index=True)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))

    episodes: Mapped[list["Episode"]] = relationship(
        back_populates="project", order_by="Episode.episode_number"
    )


class Episode(TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "episodes"
    __table_args__ = (UniqueConstraint("project_id", "episode_number", name="uq_episode_project_number"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    episode_number: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[WorkStatus] = mapped_column(
        str_enum(WorkStatus, "episode_status"), default=WorkStatus.NOT_STARTED, nullable=False
    )

    project: Mapped[Project] = relationship(back_populates="episodes")
    scenes: Mapped[list["Scene"]] = relationship(back_populates="episode", order_by="Scene.scene_number")


class Scene(TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "scenes"
    __table_args__ = (UniqueConstraint("episode_id", "scene_number", name="uq_scene_episode_number"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    episode_id: Mapped[int] = mapped_column(ForeignKey("episodes.id", ondelete="CASCADE"), nullable=False, index=True)
    scene_number: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str | None] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[WorkStatus] = mapped_column(
        str_enum(WorkStatus, "scene_status"), default=WorkStatus.NOT_STARTED, nullable=False
    )  # legacy; the shown status is derived from work (see scene_service.derive_statuses)
    # Manual override set by a lead: "on_hold" or "final" (None = automatic from assignments and reviews).
    status_override: Mapped[str | None] = mapped_column(String(20))
    duration_sec: Mapped[float | None] = mapped_column(Float)
    frame_in: Mapped[int | None] = mapped_column(Integer)
    frame_out: Mapped[int | None] = mapped_column(Integer)
    fps: Mapped[float | None] = mapped_column(Float)
    reference_links: Mapped[list] = mapped_column(JSONType, default=list, nullable=False)  # [{label, url}]
    location_id: Mapped[int | None] = mapped_column(ForeignKey("project_locations.id", ondelete="SET NULL"), index=True)

    episode: Mapped[Episode] = relationship(back_populates="scenes")
    location: Mapped["ProjectLocation | None"] = relationship()
    characters: Mapped[list["ProjectCharacter"]] = relationship(secondary="scene_characters", lazy="selectin",
                                                                order_by="ProjectCharacter.name")
    prompts: Mapped[list["ScenePrompt"]] = relationship(back_populates="scene", order_by="ScenePrompt.version",
                                                        cascade="all, delete-orphan")

    @property
    def label(self) -> str:
        return f"SC{self.scene_number:02d}"


class ProjectCharacter(Base):
    """A character in a project's cast list; scenes pick from it."""
    __tablename__ = "project_characters"
    __table_args__ = (UniqueConstraint("project_id", "name", name="uq_project_character_name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)


class ProjectLocation(Base):
    """A location in a project; each scene has at most one."""
    __tablename__ = "project_locations"
    __table_args__ = (UniqueConstraint("project_id", "name", name="uq_project_location_name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)


scene_characters = Table(
    "scene_characters", Base.metadata,
    Column("scene_id", ForeignKey("scenes.id", ondelete="CASCADE"), primary_key=True),
    Column("character_id", ForeignKey("project_characters.id", ondelete="CASCADE"), primary_key=True),
)


class ScenePrompt(Base):
    """One version of a scene's AI generation details. The highest version is the current one."""
    __tablename__ = "scene_prompts"
    __table_args__ = (UniqueConstraint("scene_id", "version", name="uq_scene_prompt_version"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    scene_id: Mapped[int] = mapped_column(ForeignKey("scenes.id", ondelete="CASCADE"), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    tool: Mapped[str | None] = mapped_column(String(80))  # e.g. Runway Gen-4, Kling, Midjourney
    seed: Mapped[str | None] = mapped_column(String(80))
    settings: Mapped[str | None] = mapped_column(Text)  # aspect ratio, motion, negative prompt, ...
    notes: Mapped[str | None] = mapped_column(Text)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, nullable=False)

    scene: Mapped[Scene] = relationship(back_populates="prompts")
