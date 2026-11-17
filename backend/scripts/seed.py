"""Seed roles + demo data.  Usage:  python -m scripts.seed"""
from app.core.database import SessionLocal
from app.services.seed import seed_demo

if __name__ == "__main__":
    with SessionLocal() as db:
        seed_demo(db)
    print("Seed complete. Demo accounts use the @studiotrack.demo domain (see README).")
