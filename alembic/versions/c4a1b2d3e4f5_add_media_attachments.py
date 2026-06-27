"""add_media_attachments

Revision ID: c4a1b2d3e4f5
Revises: bce6cf210287
Create Date: 2026-06-27 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c4a1b2d3e4f5'
down_revision: Union[str, Sequence[str], None] = 'bce6cf210287'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add the media_attachments table for the WebUI Chat media uploads."""
    op.create_table(
        'media_attachments',
        sa.Column('id', sa.String(length=32), primary_key=True),
        sa.Column('conversation_id', sa.String(length=64), nullable=False, index=True),
        sa.Column('message_id', sa.String(length=64), nullable=True),
        sa.Column('mime_type', sa.String(length=128), nullable=False),
        sa.Column('size_bytes', sa.BigInteger(), nullable=False, server_default='0'),
        sa.Column('message_type', sa.String(length=16), nullable=False, server_default='FILE'),
        sa.Column('payload', sa.LargeBinary(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    """Drop the media_attachments table."""
    op.drop_table('media_attachments')