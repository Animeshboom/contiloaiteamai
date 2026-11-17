"""Secure attachment storage.

- Extension allow-list (config), size cap enforced while streaming (never trusts Content-Length).
- Magic-byte check for common binary types so a renamed executable can't pose as a PNG/PDF/ZIP/MP4.
- Stored under a random name outside any served static path; original name kept only as metadata.
"""
import hashlib
import re
import secrets
from pathlib import Path

from fastapi import UploadFile

from app.core.config import get_settings
from app.core.errors import ValidationFailed

CHUNK = 1024 * 1024

# extension -> list of acceptable leading-byte signatures (None = text/other, no signature check)
_SIGNATURES: dict[str, list[bytes] | None] = {
    ".png": [b"\x89PNG\r\n\x1a\n"],
    ".jpg": [b"\xff\xd8\xff"],
    ".jpeg": [b"\xff\xd8\xff"],
    ".gif": [b"GIF87a", b"GIF89a"],
    ".webp": [b"RIFF"],
    ".pdf": [b"%PDF-"],
    ".zip": [b"PK\x03\x04", b"PK\x05\x06"],
    ".wav": [b"RIFF"],
    ".mp3": [b"ID3", b"\xff\xfb", b"\xff\xf3", b"\xff\xf2"],
    ".webm": [b"\x1a\x45\xdf\xa3"],
    ".mp4": None,  # ISO-BMFF: checked separately ("ftyp" at offset 4)
    ".mov": None,
    ".txt": None,
    ".json": None,
}
_EXEC_MAGIC = (b"MZ", b"\x7fELF", b"#!")


def _safe_name(name: str) -> str:
    base = Path(name).name  # drop any path components
    base = re.sub(r"[^\w.\- ()]", "_", base).strip(" .")
    return (base or "file")[:200]


def _check_signature(ext: str, head: bytes) -> None:
    if head.startswith(_EXEC_MAGIC):
        raise ValidationFailed("Executable files are not allowed")
    if ext in (".mp4", ".mov"):
        if head[4:8] != b"ftyp" and head[4:8] not in (b"moov", b"mdat", b"wide", b"free"):
            raise ValidationFailed(f"File content does not match its {ext} extension")
        return
    sigs = _SIGNATURES.get(ext)
    if sigs and not any(head.startswith(s) for s in sigs):
        raise ValidationFailed(f"File content does not match its {ext} extension")
    if ext in (".txt", ".json") and b"\x00" in head:
        raise ValidationFailed("Text files must not contain binary data")


async def store_upload(upload: UploadFile, subdir: str) -> dict:
    s = get_settings()
    original = _safe_name(upload.filename or "")
    ext = Path(original).suffix.lower()
    if ext not in s.allowed_upload_extensions:
        raise ValidationFailed(f"File type {ext or '(none)'} is not allowed. Allowed: {', '.join(s.allowed_upload_extensions)}")
    limit = s.max_upload_mb * 1024 * 1024

    target_dir = Path(s.upload_dir) / subdir
    target_dir.mkdir(parents=True, exist_ok=True)
    stored = f"{secrets.token_hex(16)}{ext}"
    path = target_dir / stored
    digest = hashlib.sha256()
    size = 0
    try:
        with path.open("wb") as fh:
            first = True
            while chunk := await upload.read(CHUNK):
                if first:
                    _check_signature(ext, chunk[:16])
                    first = False
                size += len(chunk)
                if size > limit:
                    raise ValidationFailed(f"File exceeds the {s.max_upload_mb} MB limit")
                digest.update(chunk)
                fh.write(chunk)
        if size == 0:
            raise ValidationFailed("File is empty")
    except Exception:
        path.unlink(missing_ok=True)
        raise
    return {
        "original_filename": original,
        "stored_filename": f"{subdir}/{stored}",
        "content_type": (upload.content_type or "application/octet-stream")[:120],
        "size_bytes": size,
        "sha256": digest.hexdigest(),
    }


def resolve(stored_filename: str) -> Path:
    root = Path(get_settings().upload_dir).resolve()
    path = (root / stored_filename).resolve()
    if root not in path.parents:  # defence in depth against path traversal
        raise ValidationFailed("Invalid file path")
    return path
