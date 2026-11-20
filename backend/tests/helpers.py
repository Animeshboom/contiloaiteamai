"""Shared test helpers."""
from sqlalchemy import select

from app.models import Episode, Project, Scene


def _scenes(db):
    p = db.scalar(select(Project).where(Project.code == "NEON-01"))
    ep = db.scalar(select(Episode).where(Episode.project_id == p.id, Episode.episode_number == 1))
    return p, ep, list(db.scalars(select(Scene).where(Scene.episode_id == ep.id).order_by(Scene.scene_number)))
