"""add_columns_for_recent_fr

Revision ID: bce6cf210287
Revises: b4ca5f411741
Create Date: 2026-06-27 05:01:32.270992

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'bce6cf210287'
down_revision: Union[str, Sequence[str], None] = 'b4ca5f411741'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('knowledge_base', sa.Column('knowledge_id', sa.Integer(), nullable=True))
    op.add_column('knowledge_base', sa.Column('title', sa.String(), nullable=True))
    op.add_column('knowledge_base', sa.Column('content', sa.Text(), nullable=True))
    op.add_column('knowledge_base', sa.Column('match_type', sa.String(), nullable=True))
    op.add_column('knowledge_base', sa.Column('keywords', sa.ARRAY(sa.String()), nullable=True))

    op.add_column('conversations', sa.Column('conversation_id', sa.String(), nullable=True))
    op.add_column('conversations', sa.Column('channel', sa.String(), nullable=True))
    op.add_column('conversations', sa.Column('started_at', sa.DateTime(), nullable=True))
    op.add_column('conversations', sa.Column('last_message_at', sa.DateTime(), nullable=True))
    op.add_column('conversations', sa.Column('message_count', sa.Integer(), nullable=True, server_default='0'))

    op.add_column('knowledge_chunks', sa.Column('parent_id', sa.Integer(), sa.ForeignKey('knowledge_chunks.id'), nullable=True))
    op.add_column('knowledge_chunks', sa.Column('is_parent', sa.Boolean(), nullable=True, server_default='false'))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('knowledge_chunks', 'is_parent')
    op.drop_column('knowledge_chunks', 'parent_id')
    
    op.drop_column('conversations', 'message_count')
    op.drop_column('conversations', 'last_message_at')
    op.drop_column('conversations', 'started_at')
    op.drop_column('conversations', 'channel')
    op.drop_column('conversations', 'conversation_id')
    
    op.drop_column('knowledge_base', 'keywords')
    op.drop_column('knowledge_base', 'match_type')
    op.drop_column('knowledge_base', 'content')
    op.drop_column('knowledge_base', 'title')
    op.drop_column('knowledge_base', 'knowledge_id')
