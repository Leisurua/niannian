"""Durable private account export jobs."""
from alembic import op
import sqlalchemy as sa

revision = '20261103_account_exports'
down_revision = '20261101_operational_readiness'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('account_export',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('user_id', sa.Uuid(), sa.ForeignKey('user.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('request_hash', sa.CHAR(64), nullable=False),
        sa.Column('object_key', sa.String(240), nullable=False),
        sa.Column('status', sa.String(16), nullable=False),
        sa.Column('attempts', sa.Integer(), nullable=False),
        sa.Column('lease_token', sa.Uuid()),
        sa.Column('lease_until', sa.DateTime(timezone=True)),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('retry_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('cleanup_after', sa.DateTime(timezone=True), nullable=False),
        sa.Column('purged_at', sa.DateTime(timezone=True)),
        sa.Column('error_code', sa.String(64)),
        sa.UniqueConstraint('user_id', 'request_hash', name='uq_account_export_request'),
        sa.CheckConstraint("status IN ('PENDING','RUNNING','READY','FAILED','CANCELLED','EXPIRED')", name='ck_account_export_status'),
        sa.CheckConstraint('attempts BETWEEN 0 AND 3', name='ck_account_export_attempts'),
        sa.CheckConstraint("(status = 'RUNNING' AND lease_token IS NOT NULL AND lease_until IS NOT NULL) OR "
            "(status <> 'RUNNING' AND lease_token IS NULL AND lease_until IS NULL)", name='ck_account_export_lease'))
    op.create_index('ix_account_export_queue', 'account_export', ['status', 'retry_at'])
    op.create_index('ix_account_export_cleanup', 'account_export', ['cleanup_after'])


def downgrade():
    if op.get_bind().execute(sa.text('SELECT count(*) FROM account_export WHERE purged_at IS NULL')).scalar():
        raise RuntimeError('Purge private export results before removing their durable keys')
    op.drop_table('account_export')
