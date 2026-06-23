"""initial_schema

Revision ID: b4ca5f411741
Revises: 
Create Date: 2026-06-24 01:45:06.083246

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b4ca5f411741'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # Tables with no FKs
    op.create_table('users', sa.Column('id', sa.Integer(), primary_key=True))
    op.create_table('roles', sa.Column('id', sa.Integer(), primary_key=True))
    op.create_table('knowledge_base', sa.Column('id', sa.Integer(), primary_key=True))
    op.create_table('experiments', sa.Column('id', sa.Integer(), primary_key=True))
    
    op.create_table('platform_configs', sa.Column('id', sa.Integer(), primary_key=True))
    op.create_table('security_logs', sa.Column('id', sa.Integer(), primary_key=True))
    op.create_table('emotion_history', sa.Column('id', sa.Integer(), primary_key=True))
    op.create_table('edge_cases', sa.Column('id', sa.Integer(), primary_key=True))
    op.create_table('pii_vault', sa.Column('id', sa.Integer(), primary_key=True))
    op.create_table('retry_log', sa.Column('id', sa.Integer(), primary_key=True))
    op.create_table('encryption_config', sa.Column('id', sa.Integer(), primary_key=True))
    op.create_table('schema_migrations', sa.Column('id', sa.Integer(), primary_key=True))

    # Tables with FKs to users
    op.create_table('conversations', 
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'))
    )
    op.create_table('pii_audit_log', 
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'))
    )

    # Tables with FKs to conversations
    op.create_table('messages', 
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('conversation_id', sa.Integer(), sa.ForeignKey('conversations.id')),
        sa.Column('role', sa.String()),
        sa.Column('content', sa.Text()),
        sa.Column('created_at', sa.DateTime())
    )
    op.create_table('escalation_queue', 
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('conversation_id', sa.Integer(), sa.ForeignKey('conversations.id'))
    )
    op.create_table('user_feedback', 
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('conversation_id', sa.Integer(), sa.ForeignKey('conversations.id'))
    )

    # Tables with FKs to multiple
    op.create_table('role_assignments', 
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('role_id', sa.Integer(), sa.ForeignKey('roles.id')),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'))
    )

    # Table with FK to experiments
    op.create_table('experiment_results', 
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('experiment_id', sa.Integer(), sa.ForeignKey('experiments.id'))
    )

    # knowledge_chunks
    op.create_table('knowledge_chunks', 
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('knowledge_base_id', sa.Integer(), sa.ForeignKey('knowledge_base.id')),
        sa.Column('content', sa.Text()),
        sa.Column('embedding', sa.Text()) # Temporarily create as text, we'll cast to vector
    )
    # Convert to pgvector vector(1536)
    op.execute("ALTER TABLE knowledge_chunks ALTER COLUMN embedding TYPE vector(1536) USING embedding::vector")

    # Indexes
    op.execute("CREATE INDEX idx_knowledge_chunks_embedding ON knowledge_chunks USING hnsw (embedding vector_cosine_ops) WITH (m=16, ef_construction=64) WHERE embedding IS NOT NULL")
    op.execute("CREATE INDEX idx_knowledge_chunks_content_gin ON knowledge_chunks USING gin(to_tsvector('simple', content))")


def downgrade() -> None:
    tables = [
        'knowledge_chunks', 'experiment_results', 'role_assignments',
        'user_feedback', 'escalation_queue', 'messages', 'pii_audit_log',
        'conversations', 'schema_migrations', 'encryption_config', 'retry_log',
        'pii_vault', 'edge_cases', 'emotion_history', 'security_logs',
        'platform_configs', 'experiments', 'knowledge_base', 'roles', 'users'
    ]
    for t in tables:
        op.drop_table(t)
    op.execute("DROP EXTENSION IF EXISTS vector")
