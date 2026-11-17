import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.api.routes import assignments, attendance, auth, dashboard, org, production, submissions
from app.core.config import get_settings
from app.core.database import engine
from app.core.errors import AppError
from app.core.rate_limit import limiter

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("studiotrack")

settings = get_settings()

app = FastAPI(
    title="StudioTrack AI API",
    version="0.1.0",
    description="Artist attendance, task assignment, quality review and EOD production reporting.",
)
app.state.limiter = limiter

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.exception_handler(AppError)
async def _app_error(_: Request, exc: AppError):
    return JSONResponse(status_code=exc.status_code, content={"error": exc.code, "detail": exc.message})


@app.exception_handler(RateLimitExceeded)
async def _rate_limited(_: Request, exc: RateLimitExceeded):
    return JSONResponse(status_code=429, content={"error": "rate_limited", "detail": f"Too many requests: {exc.detail}"})


@app.exception_handler(IntegrityError)
async def _integrity(_: Request, exc: IntegrityError):
    log.warning("Integrity error: %s", exc.orig.__class__.__name__)
    return JSONResponse(status_code=409, content={"error": "conflict", "detail": "This record conflicts with existing data."})


@app.exception_handler(RequestValidationError)
async def _validation(_: Request, exc: RequestValidationError):
    errors = [{"field": ".".join(str(p) for p in e["loc"][1:]), "message": e["msg"]} for e in exc.errors()]
    return JSONResponse(status_code=422, content={"error": "validation_failed", "detail": "Invalid input", "errors": errors})


@app.exception_handler(Exception)
async def _unhandled(_: Request, exc: Exception):
    log.exception("Unhandled error")  # stack trace to server logs only
    return JSONResponse(status_code=500, content={"error": "server_error", "detail": "An unexpected error occurred."})


API = "/api/v1"
app.include_router(auth.router, prefix=API)
app.include_router(org.users, prefix=API)
app.include_router(org.teams, prefix=API)
app.include_router(org.recipients, prefix=API)
app.include_router(production.router, prefix=API)
app.include_router(attendance.router, prefix=API)
app.include_router(assignments.router, prefix=API)
app.include_router(dashboard.router, prefix=API)
app.include_router(submissions.router, prefix=API)


@app.get("/api/health", tags=["meta"])
def health():
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    return {"status": "ok", "environment": settings.environment, "email_provider": settings.email_provider}
