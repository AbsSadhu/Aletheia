"""init_schema

Revision ID: c036e66a7d30
Revises: 
Create Date: 2026-06-27 00:27:31.401949

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c036e66a7d30'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = inspector.get_table_names()

    # 1. Create 'runs' if not exists
    if 'runs' not in tables:
        op.create_table(
            'runs',
            sa.Column('run_id', sa.String(), primary_key=True),
            sa.Column('status', sa.String(), nullable=False),
            sa.Column('prompt', sa.String(), nullable=False),
            sa.Column('created_at', sa.String(), nullable=False),
            sa.Column('updated_at', sa.String(), nullable=False),
            sa.Column('error_message', sa.String(), nullable=True),
            sa.Column('result_json', sa.String(), nullable=True),
        )
    
    # Create created_at index if not exists
    runs_indexes = [idx['name'] for idx in inspector.get_indexes('runs')] if 'runs' in tables else []
    if 'idx_runs_created_at' not in runs_indexes:
        op.create_index('idx_runs_created_at', 'runs', ['created_at'])

    # 2. Create 'portfolios' if not exists
    if 'portfolios' not in tables:
        op.create_table(
            'portfolios',
            sa.Column('name', sa.String(), primary_key=True),
            sa.Column('base_currency', sa.String(), nullable=False),
            sa.Column('holdings_json', sa.String(), nullable=False),
            sa.Column('created_at', sa.String(), nullable=False),
            sa.Column('updated_at', sa.String(), nullable=False),
        )

    # 3. Create 'agent_events' if not exists
    if 'agent_events' not in tables:
        op.create_table(
            'agent_events',
            sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column('run_id', sa.String(), sa.ForeignKey('runs.run_id', ondelete='CASCADE'), nullable=False),
            sa.Column('agent', sa.String(), nullable=False),
            sa.Column('message', sa.String(), nullable=False),
            sa.Column('timestamp', sa.String(), nullable=False),
            sa.Column('payload_json', sa.String(), nullable=True),
        )

    events_indexes = [idx['name'] for idx in inspector.get_indexes('agent_events')] if 'agent_events' in tables else []
    if 'idx_agent_events_run_id' not in events_indexes:
        op.create_index('idx_agent_events_run_id', 'agent_events', ['run_id'])
    if 'idx_agent_events_timestamp' not in events_indexes:
        op.create_index('idx_agent_events_timestamp', 'agent_events', ['timestamp'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('idx_agent_events_timestamp', table_name='agent_events')
    op.drop_index('idx_agent_events_run_id', table_name='agent_events')
    op.drop_table('agent_events')
    op.drop_table('portfolios')
    op.drop_index('idx_runs_created_at', table_name='runs')
    op.drop_table('runs')

