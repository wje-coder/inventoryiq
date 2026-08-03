"""Local filesystem storage for uploaded dataset files.

Security model: the user-supplied filename is NEVER used to build a
filesystem path. Every file is written under a per-dataset directory
named after a server-generated UUID, with a server-generated filename
(`{uuid4}{extension}`). The original filename is sanitized separately
and kept only as a display string in the database.
"""

import re
import unicodedata
import uuid
from pathlib import Path

from fastapi import UploadFile

from app.core.config import get_settings

settings = get_settings()

_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")
_UNSAFE_CHARS = re.compile(r"[^A-Za-z0-9._ -]")
_MAX_DISPLAY_FILENAME_LENGTH = 255


class FileTooLargeError(Exception):
    """Raised mid-stream when an upload exceeds the configured max size."""


def get_storage_root() -> Path:
    root = Path(settings.dataset_storage_dir)
    if not root.is_absolute():
        # Resolve relative to the backend package's parent (the
        # `backend/` directory), not the process's current working
        # directory, so behavior doesn't depend on how uvicorn was
        # launched.
        root = Path(__file__).resolve().parents[2] / root
    root.mkdir(parents=True, exist_ok=True)
    return root


def sanitize_original_filename(filename: str) -> str:
    """Produce a display-safe version of a user-supplied filename.

    Strips any directory components, control characters, and anything
    that isn't a conservative safe-character set. The result is used
    for display purposes only and is never joined onto a filesystem path.
    """
    name = unicodedata.normalize("NFKC", filename or "")
    # Strip any path components the client might have sent (both
    # separators, defensively, regardless of host OS).
    name = name.replace("\\", "/").split("/")[-1]
    name = _CONTROL_CHARS.sub("", name)
    name = _UNSAFE_CHARS.sub("_", name).strip()
    if not name or name in {".", ".."}:
        name = "upload"
    return name[:_MAX_DISPLAY_FILENAME_LENGTH]


def generate_stored_filename(extension: str) -> str:
    safe_extension = extension.lower().lstrip(".")
    return f"{uuid.uuid4().hex}.{safe_extension}"


def dataset_relative_dir(dataset_id: uuid.UUID) -> Path:
    return Path(str(dataset_id))


def resolve_storage_path(relative_path: str) -> Path:
    """Join a DB-stored relative path onto the storage root, guarding
    against path traversal even though relative_path is always
    server-generated, never taken directly from user input."""
    root = get_storage_root().resolve()
    candidate = (root / relative_path).resolve()
    if root not in candidate.parents and candidate != root:
        raise ValueError("Resolved storage path escapes the storage root.")
    return candidate


async def save_upload_stream(upload_file: UploadFile, relative_path: str) -> int:
    """Stream an UploadFile to disk, enforcing max_upload_size_bytes on
    actual bytes written (not a client-supplied Content-Length header).
    Cleans up any partial file if the size limit is exceeded or the
    write otherwise fails.
    """
    destination = resolve_storage_path(relative_path)
    destination.parent.mkdir(parents=True, exist_ok=True)

    bytes_written = 0
    chunk_size = 1024 * 1024
    try:
        with destination.open("wb") as out_file:
            while True:
                chunk = await upload_file.read(chunk_size)
                if not chunk:
                    break
                bytes_written += len(chunk)
                if bytes_written > settings.max_upload_size_bytes:
                    raise FileTooLargeError(
                        f"File exceeds the maximum allowed size of "
                        f"{settings.max_upload_size_bytes} bytes."
                    )
                out_file.write(chunk)
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    finally:
        await upload_file.close()

    return bytes_written


def delete_file(relative_path: str | None) -> None:
    """Best-effort delete; a missing file is not an error."""
    if not relative_path:
        return
    try:
        resolve_storage_path(relative_path).unlink(missing_ok=True)
    except ValueError:
        # Should never happen for server-generated paths; never let a
        # storage inconsistency block a delete/cleanup operation.
        pass
