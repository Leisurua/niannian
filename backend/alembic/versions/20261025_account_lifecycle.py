"""Account erasure receipts and durable possible-provider-copy inventory."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = '20261025_account_lifecycle'
down_revision = '20261024_interaction_stats'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('account_deletion',
        sa.Column('id', sa.UUID(), primary_key=True),
        sa.Column('user_id', sa.UUID(), sa.ForeignKey('user.id', ondelete='RESTRICT'), nullable=False, unique=True),
        sa.Column('receipt_hash', sa.CHAR(64), nullable=False, unique=True),
        sa.Column('local_status', sa.String(16), nullable=False),
        sa.Column('requested_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('local_erased_at', sa.DateTime(timezone=True)),
        sa.Column('retry_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('last_error_code', sa.String(64)),
        sa.Column('backup_due_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('backup_confirmed_at', sa.DateTime(timezone=True)),
        sa.Column('backup_evidence_hash', sa.CHAR(64)),
        sa.CheckConstraint("local_status IN ('PENDING','RETRY','ERASED')", name='ck_account_deletion_local'))
    op.create_table('provider_copy',
        sa.Column('id', sa.UUID(), primary_key=True),
        sa.Column('user_id', sa.UUID(), sa.ForeignKey('user.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('provider', sa.String(160), nullable=False),
        sa.Column('first_possible_send_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('last_possible_send_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('confirmed_at', sa.DateTime(timezone=True)),
        sa.Column('evidence_hash', sa.CHAR(64)),
        sa.Column('resource_refs', JSONB(), nullable=False, server_default='[]'),
        sa.UniqueConstraint('user_id', 'provider', name='uq_provider_copy_user'))
    # Historical providers were not inventoried. Never infer zero copies from a
    # current Mock setting or from conversations/notifications already expired.
    op.execute("""INSERT INTO provider_copy (id, user_id, provider, first_possible_send_at, last_possible_send_at)
        SELECT id, id, 'LEGACY_UNVERIFIED', created_at, now() FROM "user"
    """)


def downgrade():
    if op.get_bind().execute(sa.text('SELECT EXISTS (SELECT 1 FROM account_deletion) OR EXISTS (SELECT 1 FROM provider_copy)')).scalar():
        raise RuntimeError('Cannot discard outstanding lifecycle records')
    op.drop_table('provider_copy')
    op.drop_table('account_deletion')
