"""Durable worker heartbeat for dependency-aware readiness."""
from alembic import op
import sqlalchemy as sa

revision = '20261101_operational_readiness'
down_revision = '20261101_report_semantics'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('service_heartbeat',
        sa.Column('service', sa.String(32), primary_key=True),
        sa.Column('instance_id', sa.String(64), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('last_seen_at', sa.DateTime(timezone=True), nullable=False))
    op.create_index('ix_service_heartbeat_last_seen_at', 'service_heartbeat', ['last_seen_at'])


def downgrade():
    op.drop_index('ix_service_heartbeat_last_seen_at', table_name='service_heartbeat')
    op.drop_table('service_heartbeat')
