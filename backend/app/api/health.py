"""Health check endpoints."""

import logging

from fastapi import APIRouter

from app.db.session import check_db_connection

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict[str, str]:
    """Report service and database health.

    Always returns 200 so orchestrators can reach the endpoint; the
    payload distinguishes between the API being up and the database
    being reachable.
    """
    db_ok = True
    try:
        await check_db_connection()
    except Exception:  # noqa: BLE001 - deliberately broad for a health probe
        logger.exception("Database health check failed")
        db_ok = False

    return {
        "status": "ok",
        "database": "ok" if db_ok else "unavailable",
    }
