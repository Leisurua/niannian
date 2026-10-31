"""Family-owned voice versions, elder preferences and durable cleanup."""
from alembic import op
import sqlalchemy as sa

revision = '20261029_family_voices'
down_revision = '20261026_avatar_jobs'
branch_labels = depends_on = None
OLD = "'MEMORY_INDEX','MEMORY_CLEANUP','FILE_CLEANUP','CONVERSATION_SUMMARY','CONVERSATION_SUMMARY_CLEANUP','NOTIFICATION_DISPATCH','SIGNAL_CLEANUP','NOTIFICATION_CLEANUP','AVATAR_GENERATE'"


def upgrade():
    op.create_table('voice_profile',
        sa.Column('id', sa.UUID(), primary_key=True),
        sa.Column('family_id', sa.UUID(), sa.ForeignKey('family.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('owner_user_id', sa.UUID(), sa.ForeignKey('user.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('creator_user_id', sa.UUID(), sa.ForeignKey('user.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('display_name', sa.String(60), nullable=False),
        sa.Column('status', sa.String(16), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('sample_key', sa.String(200)),
        sa.Column('sample_hash', sa.String(64)),
        sa.Column('preview_key', sa.String(200)),
        sa.Column('provider_voice_id', sa.String(200)),
        sa.Column('provider_workspace', sa.String(100)),
        sa.Column('provider_model', sa.String(64), nullable=False),
        sa.Column('approved_at', sa.DateTime(timezone=True)),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True)),
        sa.Column('error_code', sa.String(64)),
        sa.CheckConstraint("status IN ('UPLOADING','PENDING','QUEUED','GENERATING','READY','ACTIVE','FAILED','REVOKED','DELETED')", name='ck_voice_status'))
    op.create_index('uq_voice_active', 'voice_profile', ['family_id', 'owner_user_id'], unique=True,
                    postgresql_where=sa.text("status = 'ACTIVE'"))
    op.create_table('voice_preference',
        sa.Column('family_id', sa.UUID(), sa.ForeignKey('family.id', ondelete='RESTRICT'), primary_key=True),
        sa.Column('owner_user_id', sa.UUID(), sa.ForeignKey('user.id', ondelete='RESTRICT'), primary_key=True),
        sa.Column('voice_profile_id', sa.UUID(), sa.ForeignKey('voice_profile.id', ondelete='SET NULL')),
        sa.Column('cloud_tts_allowed', sa.Boolean(), nullable=False))
    op.drop_constraint('ck_task_kind', 'task_outbox', type_='check')
    op.create_check_constraint('ck_task_kind', 'task_outbox', f"kind IN ({OLD},'VOICE_GENERATE','VOICE_CLEANUP')")


def downgrade():
    if op.get_bind().execute(sa.text("SELECT EXISTS(SELECT 1 FROM voice_profile WHERE status != 'DELETED')")).scalar():
        raise RuntimeError('Clean up family voice assets and provider resources before downgrade')
    op.execute("DELETE FROM task_outbox WHERE kind IN ('VOICE_GENERATE','VOICE_CLEANUP')")
    op.drop_table('voice_preference')
    op.drop_table('voice_profile')
    op.drop_constraint('ck_task_kind', 'task_outbox', type_='check')
    op.create_check_constraint('ck_task_kind', 'task_outbox', f"kind IN ({OLD})")
