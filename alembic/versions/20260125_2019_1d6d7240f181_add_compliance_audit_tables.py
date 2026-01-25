"""Add compliance audit tables

Revision ID: 1d6d7240f181
Revises: de92c6e8c38a
Create Date: 2026-01-25 20:19:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '1d6d7240f181'
down_revision: Union[str, None] = 'de92c6e8c38a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add YouTube Partner Program compliance audit tables.

    Story 7.7 - YouTube Compliance Enforcement (Fix Issue #2)

    Creates:
    1. content_uniqueness_scores: Track uniqueness validation results over time
    2. upload_frequency_log: Track upload timing patterns for organic scheduling
    3. compliance_violations: Track compliance violation history and resolutions
    """
    # 1. Create content_uniqueness_scores table
    op.create_table(
        'content_uniqueness_scores',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('task_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('tasks.id', ondelete='CASCADE'), nullable=False),
        sa.Column('channel_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('channels.id', ondelete='CASCADE'), nullable=False),
        sa.Column('visual_uniqueness_score', sa.Float, nullable=False, comment='Perceptual hash dissimilarity (0.0-1.0)'),
        sa.Column('narrative_uniqueness_score', sa.Float, nullable=False, comment='Story structure dissimilarity (0.0-1.0)'),
        sa.Column('metadata_uniqueness_score', sa.Float, nullable=False, comment='Title/description/tags dissimilarity (0.0-1.0)'),
        sa.Column('overall_uniqueness_score', sa.Float, nullable=False, comment='Average of all dimensions'),
        sa.Column('passes_threshold', sa.Boolean, nullable=False, comment='True if all dimensions >= 70%'),
        sa.Column('compared_against_videos', sa.Integer, nullable=False, comment='Number of recent videos compared'),
        sa.Column('validation_timestamp', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        comment='Tracks content uniqueness validation results for YouTube compliance auditing'
    )

    # Indexes for querying uniqueness history by channel
    op.create_index('ix_uniqueness_scores_channel_id', 'content_uniqueness_scores', ['channel_id'])
    op.create_index('ix_uniqueness_scores_task_id', 'content_uniqueness_scores', ['task_id'])
    op.create_index('ix_uniqueness_scores_validation_timestamp', 'content_uniqueness_scores', ['validation_timestamp'])

    # 2. Create upload_frequency_log table
    op.create_table(
        'upload_frequency_log',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('task_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('tasks.id', ondelete='CASCADE'), nullable=False),
        sa.Column('channel_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('channels.id', ondelete='CASCADE'), nullable=False),
        sa.Column('scheduled_upload_time', sa.DateTime(timezone=True), nullable=False, comment='Organically scheduled upload time'),
        sa.Column('actual_upload_time', sa.DateTime(timezone=True), nullable=True, comment='Actual time video was uploaded'),
        sa.Column('upload_window', sa.String(50), nullable=False, comment='Time-of-day window (morning/afternoon/evening/night)'),
        sa.Column('hours_since_last_upload', sa.Float, nullable=True, comment='Hours since previous upload on this channel'),
        sa.Column('daily_upload_count', sa.Integer, nullable=False, comment='Number of uploads today before this one'),
        sa.Column('frequency_throttled', sa.Boolean, nullable=False, comment='True if upload was delayed for frequency limits'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        comment='Tracks upload timing patterns for organic frequency enforcement'
    )

    # Indexes for analyzing upload patterns
    op.create_index('ix_upload_frequency_channel_id', 'upload_frequency_log', ['channel_id'])
    op.create_index('ix_upload_frequency_scheduled_time', 'upload_frequency_log', ['scheduled_upload_time'])
    op.create_index('ix_upload_frequency_actual_time', 'upload_frequency_log', ['actual_upload_time'])

    # 3. Create compliance_violations table
    op.create_table(
        'compliance_violations',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('task_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('tasks.id', ondelete='CASCADE'), nullable=False),
        sa.Column('channel_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('channels.id', ondelete='CASCADE'), nullable=False),
        sa.Column('violation_type', sa.String(100), nullable=False, comment='Type: uniqueness_failure, duplicate_content, missing_evidence, ai_disclosure_failed'),
        sa.Column('violation_details', postgresql.JSON, nullable=False, comment='Detailed validation results and failure reasons'),
        sa.Column('violation_timestamp', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('resolved', sa.Boolean, nullable=False, default=False, comment='True if violation was fixed and task requeued'),
        sa.Column('resolution_timestamp', sa.DateTime(timezone=True), nullable=True, comment='When violation was resolved'),
        sa.Column('resolution_notes', sa.Text, nullable=True, comment='How the violation was resolved'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()'), onupdate=sa.text('now()')),
        comment='Tracks compliance violations for auditing and pattern analysis'
    )

    # Indexes for violation reporting
    op.create_index('ix_violations_channel_id', 'compliance_violations', ['channel_id'])
    op.create_index('ix_violations_violation_type', 'compliance_violations', ['violation_type'])
    op.create_index('ix_violations_resolved', 'compliance_violations', ['resolved'])
    op.create_index('ix_violations_timestamp', 'compliance_violations', ['violation_timestamp'])


def downgrade() -> None:
    """Remove compliance audit tables.

    WARNING: Downgrading will lose all compliance audit history.
    """
    # Drop indexes first
    op.drop_index('ix_violations_timestamp', table_name='compliance_violations')
    op.drop_index('ix_violations_resolved', table_name='compliance_violations')
    op.drop_index('ix_violations_violation_type', table_name='compliance_violations')
    op.drop_index('ix_violations_channel_id', table_name='compliance_violations')

    op.drop_index('ix_upload_frequency_actual_time', table_name='upload_frequency_log')
    op.drop_index('ix_upload_frequency_scheduled_time', table_name='upload_frequency_log')
    op.drop_index('ix_upload_frequency_channel_id', table_name='upload_frequency_log')

    op.drop_index('ix_uniqueness_scores_validation_timestamp', table_name='content_uniqueness_scores')
    op.drop_index('ix_uniqueness_scores_task_id', table_name='content_uniqueness_scores')
    op.drop_index('ix_uniqueness_scores_channel_id', table_name='content_uniqueness_scores')

    # Drop tables
    op.drop_table('compliance_violations')
    op.drop_table('upload_frequency_log')
    op.drop_table('content_uniqueness_scores')
