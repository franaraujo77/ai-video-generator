"""Migrate Task model to 26-status workflow with full metadata.

This migration replaces the simple Task model with the comprehensive 26-status
workflow implementation. Changes include:
    - Drop old tasks table (preserves no data - Epic 1 was dev/test only)
    - Create PostgreSQL enums for TaskStatus (26 values) and PriorityLevel (3 values)
    - Create new tasks table with full schema:
        - notion_page_id (unique constraint for Notion sync)
        - title, topic, story_direction (video metadata)
        - status (enum, 26 statuses)
        - priority (enum, high/normal/low)
        - error_log (nullable text)
        - youtube_url (nullable)
        - Foreign key to channels.id (UUID, not channel_id string)
    - Create comprehensive indexes for queue queries

Revision ID: 007_migrate_task_26_status
Revises: 006_add_task_model
Create Date: 2026-01-13

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "007_migrate_task_26_status"
down_revision: str | None = "006_add_task_model"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Replace simple Task model with 26-status workflow implementation."""
    # Step 1: Drop old tasks table and indexes
    # Safe because Epic 1 was development only, no production data exists
    op.drop_index("idx_tasks_pending", table_name="tasks")
    op.drop_index("ix_tasks_channel_id_status", table_name="tasks")
    op.drop_index("ix_tasks_status", table_name="tasks")
    op.drop_index("ix_tasks_channel_id", table_name="tasks")
    op.drop_table("tasks")

    # Step 2: Create PostgreSQL enums for status and priority
    # TaskStatus enum (26 values in exact pipeline order)
    task_status_enum = postgresql.ENUM(
        # Initial states
        "draft",
        "queued",
        "claimed",
        # Asset generation phase (Step 1)
        "generating_assets",
        "assets_ready",
        "assets_approved",
        # Composite creation phase (Step 2)
        "generating_composites",
        "composites_ready",
        # Video generation phase (Step 3)
        "generating_video",
        "video_ready",
        "video_approved",
        # Audio generation phase (Step 4)
        "generating_audio",
        "audio_ready",
        "audio_approved",
        # Sound effects phase (Step 5)
        "generating_sfx",
        "sfx_ready",
        # Assembly phase (Step 6)
        "assembling",
        "assembly_ready",
        # Review and approval phase (Step 7)
        "final_review",
        "approved",
        # YouTube upload phase (Step 8)
        "uploading",
        "published",
        # Error states (recoverable)
        "asset_error",
        "video_error",
        "audio_error",
        "upload_error",
        name="taskstatus",
    )
    task_status_enum.create(op.get_bind())

    # PriorityLevel enum (3 values)
    priority_level_enum = postgresql.ENUM(
        "high",
        "normal",
        "low",
        name="prioritylevel",
    )
    priority_level_enum.create(op.get_bind())

    # Step 3: Create new tasks table with comprehensive schema
    op.create_table(
        "tasks",
        # Primary key
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
        ),
        # Foreign key to channels.id (UUID, NOT channel_id string)
        # CRITICAL: References channels.id (the UUID PK), not channels.channel_id
        sa.Column(
            "channel_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        # Notion integration (unique constraint)
        sa.Column(
            "notion_page_id",
            sa.String(32),
            unique=True,
            nullable=False,
        ),
        # Content metadata
        sa.Column(
            "title",
            sa.String(255),
            nullable=False,
        ),
        sa.Column(
            "topic",
            sa.String(500),
            nullable=False,
        ),
        sa.Column(
            "story_direction",
            sa.Text,
            nullable=False,
        ),
        # Workflow state (26-status enum)
        sa.Column(
            "status",
            task_status_enum,
            nullable=False,
            server_default="draft",
        ),
        # Priority queue management
        sa.Column(
            "priority",
            priority_level_enum,
            nullable=False,
            server_default="normal",
        ),
        # Error tracking (nullable)
        sa.Column(
            "error_log",
            sa.Text,
            nullable=True,
        ),
        # YouTube output (nullable)
        sa.Column(
            "youtube_url",
            sa.String(255),
            nullable=True,
        ),
        # Timestamps
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        # Foreign key constraint to channels.id (ondelete='RESTRICT')
        sa.ForeignKeyConstraint(
            ["channel_id"],
            ["channels.id"],
            name="fk_tasks_channel_id",
            ondelete="RESTRICT",
        ),
    )

    # Step 4: Create indexes for efficient queue queries
    # Individual column indexes
    op.create_index(
        "ix_tasks_status",
        "tasks",
        ["status"],
    )
    op.create_index(
        "ix_tasks_channel_id",
        "tasks",
        ["channel_id"],
    )
    op.create_index(
        "ix_tasks_created_at",
        "tasks",
        ["created_at"],
    )
    op.create_index(
        "ix_tasks_notion_page_id",
        "tasks",
        ["notion_page_id"],
        unique=True,
    )

    # Composite index for capacity queries (channel + status filtering)
    op.create_index(
        "ix_tasks_channel_id_status",
        "tasks",
        ["channel_id", "status"],
    )

    # Partial index on status='queued' for fast worker claims
    op.create_index(
        "idx_tasks_queued",
        "tasks",
        ["channel_id", "priority", "created_at"],
        postgresql_where=sa.text("status = 'queued'"),
    )


def downgrade() -> None:
    """Revert to simple Task model (data loss - Epic 2 development only)."""
    # Drop new tasks table and indexes
    op.drop_index("idx_tasks_queued", table_name="tasks")
    op.drop_index("ix_tasks_channel_id_status", table_name="tasks")
    op.drop_index("ix_tasks_notion_page_id", table_name="tasks")
    op.drop_index("ix_tasks_created_at", table_name="tasks")
    op.drop_index("ix_tasks_channel_id", table_name="tasks")
    op.drop_index("ix_tasks_status", table_name="tasks")
    op.drop_table("tasks")

    # Drop enums
    op.execute("DROP TYPE IF EXISTS taskstatus")
    op.execute("DROP TYPE IF EXISTS prioritylevel")

    # Recreate old simple tasks table (Epic 1 version)
    op.create_table(
        "tasks",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("channel_id", sa.String(50), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["channel_id"],
            ["channels.channel_id"],
            name="fk_tasks_channel_id",
        ),
    )

    # Recreate old indexes
    op.create_index(
        "ix_tasks_channel_id",
        "tasks",
        ["channel_id"],
    )
    op.create_index(
        "ix_tasks_status",
        "tasks",
        ["status"],
    )
    op.create_index(
        "ix_tasks_channel_id_status",
        "tasks",
        ["channel_id", "status"],
    )
    op.create_index(
        "idx_tasks_pending",
        "tasks",
        ["channel_id"],
        postgresql_where=sa.text("status = 'pending'"),
    )
