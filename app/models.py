"""SQLAlchemy 2.0 ORM models.

This module contains all SQLAlchemy models for the orchestration layer.
All models use the Mapped[type] annotation pattern required by SQLAlchemy 2.0.

Models are kept in a single file until ~500 lines, then split by domain.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    """Get current UTC datetime (timezone-aware)."""
    return datetime.now(UTC)


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""

    pass


class Channel(Base):
    """YouTube channel configuration and tracking.

    Each channel represents a distinct YouTube channel with its own
    credentials, voice settings, and content configuration.

    Attributes:
        id: Internal UUID primary key.
        channel_id: Business identifier for the channel (e.g., "poke1", "nature1").
        channel_name: Human-readable display name.
        created_at: Timestamp when channel was registered.
        updated_at: Timestamp of last configuration change.
        is_active: Whether channel is enabled for video generation.
    """

    __tablename__ = "channels"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    channel_id: Mapped[str] = mapped_column(
        String(50),
        unique=True,
        nullable=False,
        index=True,
    )
    channel_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        index=True,  # Index for filtering active/inactive channels
    )

    def __repr__(self) -> str:
        """Return string representation for debugging."""
        return f"<Channel(channel_id={self.channel_id!r}, name={self.channel_name!r})>"
