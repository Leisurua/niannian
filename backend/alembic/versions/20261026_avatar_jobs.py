"""Private photo-to-avatar jobs; assets reuse file_asset cleanup and retention."""
from alembic import op
import sqlalchemy as sa

revision = '20261026_avatar_jobs'
down_revision = '20261025_account_lifecycle'
branch_labels = None
depends_on = None
OLD_KINDS = "'MEMORY_INDEX','MEMORY_CLEANUP','FILE_CLEANUP','CONVERSATION_SUMMARY','CONVERSATION_SUMMARY_CLEANUP','NOTIFICATION_DISPATCH','SIGNAL_CLEANUP','NOTIFICATION_CLEANUP'"


def upgrade():
    op.create_table('avatar_job',
        sa.Column('id', sa.UUID(), primary_key=True),
        sa.Column('family_id', sa.UUID(), sa.ForeignKey('family.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('owner_user_id', sa.UUID(), sa.ForeignKey('user.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('consent_id', sa.UUID(), nullable=False),
        sa.Column('provider_id', sa.String(64), nullable=False),
        sa.Column('source_id', sa.UUID(), sa.ForeignKey('file_asset.id', ondelete='SET NULL')),
        sa.Column('pack_id', sa.UUID(), sa.ForeignKey('file_asset.id', ondelete='SET NULL')),
        sa.Column('preview_id', sa.UUID(), sa.ForeignKey('file_asset.id', ondelete='SET NULL')),
        sa.Column('status', sa.String(16), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('error_code', sa.String(64)),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True)),
        sa.Column('confirmed_at', sa.DateTime(timezone=True)),
        sa.Column('deleted_at', sa.DateTime(timezone=True)),
        sa.CheckConstraint("status IN ('UPLOADING','QUEUED','STYLIZING','PREPARING','RENDERING','READY','ACTIVE','FAILED','CANCELLED')", name='ck_avatar_status'),
        sa.CheckConstraint('version > 0', name='ck_avatar_version'))
    op.create_index('ix_avatar_owner', 'avatar_job', ['family_id', 'owner_user_id', 'created_at'])
    op.create_index('uq_avatar_active', 'avatar_job', ['family_id', 'owner_user_id'], unique=True,
        postgresql_where=sa.text("status = 'ACTIVE'"))
    op.drop_constraint('ck_task_kind', 'task_outbox', type_='check')
    op.create_check_constraint('ck_task_kind', 'task_outbox', f"kind IN ({OLD_KINDS},'AVATAR_GENERATE')")


def downgrade():
    if op.get_bind().execute(sa.text('SELECT EXISTS (SELECT 1 FROM avatar_job)')).scalar():
        raise RuntimeError('Remove avatar jobs and private assets before downgrading')
    op.execute("DELETE FROM task_outbox WHERE kind='AVATAR_GENERATE'")
    op.drop_constraint('ck_task_kind', 'task_outbox', type_='check')
    op.create_check_constraint('ck_task_kind', 'task_outbox', f"kind IN ({OLD_KINDS})")
    op.drop_table('avatar_job')
