"""Shared pytest fixtures.

Tests run against an isolated in-memory SQLite database (via aiosqlite)
rather than the real Postgres container, so the suite is fast and has no
external dependencies. Tables are created directly from the SQLAlchemy
metadata (bypassing Alembic, which is exercised separately against
Postgres when the Docker Compose stack starts).
"""

import shutil
import tempfile
from collections.abc import AsyncGenerator, Generator

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings
from app.db.base import Base
from app.db.session import get_db
from app.main import app

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture(autouse=True, scope="session")
def _isolated_dataset_storage() -> Generator[None, None, None]:
    """Redirect dataset file storage to a throwaway temp directory for the
    whole test session, instead of writing into the real (gitignored but
    still on-disk) backend/var/datasets/ directory every test run.
    """
    temp_dir = tempfile.mkdtemp(prefix="inventoryiq-test-datasets-")
    settings = get_settings()
    original_dir = settings.dataset_storage_dir
    settings.dataset_storage_dir = temp_dir
    try:
        yield
    finally:
        settings.dataset_storage_dir = original_dir
        shutil.rmtree(temp_dir, ignore_errors=True)


@pytest_asyncio.fixture
async def db_engine() -> AsyncGenerator[AsyncEngine, None]:
    engine = create_async_engine(
        TEST_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(db_engine: AsyncEngine) -> AsyncGenerator[AsyncSession, None]:
    session_factory = async_sessionmaker(bind=db_engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session


@pytest.fixture
def client(db_engine: AsyncEngine) -> Generator[TestClient, None, None]:
    session_factory = async_sessionmaker(bind=db_engine, expire_on_commit=False)

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
