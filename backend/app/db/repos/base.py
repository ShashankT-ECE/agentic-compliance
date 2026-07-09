"""Repository base class — V2 M4.

Provides a shared session-accepting pattern for all repositories.
Each repository receives an ``AsyncSession`` from the caller (never
creates its own), so transaction boundaries are explicit at the call site.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession


class BaseRepository:
    """Base for all PostgreSQL repositories.

    Subclasses accept an ``AsyncSession`` in their constructor and use
    ``self._session`` for all database operations.  The session is owned
    by the caller — repositories never commit or roll back.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
