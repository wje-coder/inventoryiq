"""Declarative base shared by all ORM models.

Kept separate from session.py so Alembic's env.py can import model
metadata without also importing the live engine/session machinery.
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
