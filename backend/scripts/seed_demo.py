"""Seed demo studio data for local development.

Usage:
    python -m scripts.seed_demo
"""
import sys
from app.core.database import SessionLocal
from tests.fixtures import seed_demo


def main() -> None:
    print("Seeding StudioTrack AI demo data...")
    with SessionLocal() as db:
        seed_demo(db)
    print("Demo data seeded successfully!")
    print("\nAvailable demo login accounts:")
    print("  - Admin:      admin@studiotrack.demo        (Password: Admin@12345)")
    print("  - Anim Lead:  lead.anim@studiotrack.demo    (Password: Lead@12345)")
    print("  - Comp Lead:  lead.comp@studiotrack.demo    (Password: Lead@12345)")
    print("  - Artist:     artist.arjun@studiotrack.demo (Password: Artist@12345)")
    print("  - Artist:     artist.sara@studiotrack.demo  (Password: Artist@12345)")
    print("  - Artist:     artist.nina@studiotrack.demo  (Password: Artist@12345)")


if __name__ == "__main__":
    main()

