import enum


class RoleName(str, enum.Enum):
    ADMIN = "admin"
    TEAM_LEAD = "team_lead"
    ARTIST = "artist"


class ProjectType(str, enum.Enum):
    FEATURE_FILM = "feature_film"
    SERIES = "series"
    SHORT_FILM = "short_film"
    COMMERCIAL = "commercial"
    MUSIC_VIDEO = "music_video"
    OTHER = "other"


class ProjectStatus(str, enum.Enum):
    PLANNING = "planning"
    ACTIVE = "active"
    ON_HOLD = "on_hold"
    COMPLETED = "completed"
    ARCHIVED = "archived"


class WorkStatus(str, enum.Enum):
    """Status for episodes and scenes."""
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    IN_REVIEW = "in_review"
    APPROVED = "approved"
    COMPLETED = "completed"


class Priority(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class AssignmentStatus(str, enum.Enum):
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    SUBMITTED = "submitted"  # Submitted for Review
    APPROVED = "approved"
    REVISION_REQUIRED = "revision_required"  # Rejected / Revision Required
    COMPLETED = "completed"


class AttendanceStatus(str, enum.Enum):
    PRESENT = "present"
    ABSENT = "absent"
    HALF_DAY = "half_day"
    LEAVE = "leave"


class SubmissionStatus(str, enum.Enum):
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    REJECTED = "rejected"


class DeliverableStatus(str, enum.Enum):
    SUBMITTED = "submitted"
    APPROVED = "approved"
    REJECTED = "rejected"


class ReviewDecision(str, enum.Enum):
    APPROVED = "approved"
    REJECTED = "rejected"


class EmailStatus(str, enum.Enum):
    PENDING = "pending"
    SENT = "sent"
    DRAFTED = "drafted"
    FAILED = "failed"
    BLOCKED = "blocked"  # e.g. unauthorized recipient


class ReportStatus(str, enum.Enum):
    DRAFT = "draft"
    APPROVED = "approved"
    SENT = "sent"
    FAILED = "failed"
