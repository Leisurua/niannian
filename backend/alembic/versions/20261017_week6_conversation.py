from alembic import op
import sqlalchemy as sa

revision = '20261017_week6_conversation'
down_revision = '20261015_week5_rag_tasks'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('conversation', sa.Column('summary_version', sa.Integer(), nullable=False, server_default='1'))
    op.create_check_constraint('ck_conversation_summary_version', 'conversation', 'summary_version > 0')
    op.drop_constraint('ck_task_kind', 'task_outbox', type_='check')
    op.create_check_constraint('ck_task_kind', 'task_outbox',
        "kind IN ('MEMORY_INDEX','MEMORY_CLEANUP','FILE_CLEANUP','CONVERSATION_SUMMARY','CONVERSATION_SUMMARY_CLEANUP')")
    op.create_table('proactive_preference',
        sa.Column('family_id', sa.UUID(), sa.ForeignKey('family.id', ondelete='RESTRICT'), primary_key=True),
        sa.Column('owner_user_id', sa.UUID(), sa.ForeignKey('user.id', ondelete='RESTRICT'), primary_key=True),
        sa.Column('timezone', sa.String(64), nullable=False),
        sa.Column('window_start', sa.Time(), nullable=False), sa.Column('window_end', sa.Time(), nullable=False),
        sa.Column('quiet_start', sa.Time()), sa.Column('quiet_end', sa.Time()),
        sa.Column('daily_cap', sa.SmallInteger(), nullable=False, server_default='0'),
        sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('proposed_by_user_id', sa.UUID(), sa.ForeignKey('user.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('confirmed_by_user_id', sa.UUID(), sa.ForeignKey('user.id', ondelete='RESTRICT')),
        sa.Column('confirmed_version', sa.Integer()), sa.Column('paused_on', sa.Date()),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint('daily_cap BETWEEN 0 AND 3', name='ck_proactive_cap'),
        sa.CheckConstraint('version > 0', name='ck_proactive_version'),
        sa.CheckConstraint('(quiet_start IS NULL) = (quiet_end IS NULL)', name='ck_proactive_quiet'),
        sa.CheckConstraint('(confirmed_by_user_id IS NULL AND confirmed_version IS NULL) OR '
            '(confirmed_by_user_id IS NOT NULL AND confirmed_version IS NOT NULL AND confirmed_by_user_id = owner_user_id AND confirmed_version = version)', name='ck_proactive_confirmation'))
    op.create_table('proactive_daily_counter',
        sa.Column('family_id', sa.UUID(), primary_key=True), sa.Column('owner_user_id', sa.UUID(), primary_key=True),
        sa.Column('local_date', sa.Date(), primary_key=True),
        sa.Column('used_count', sa.SmallInteger(), nullable=False, server_default='0'),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['family_id', 'owner_user_id'], ['proactive_preference.family_id', 'proactive_preference.owner_user_id'], ondelete='CASCADE'),
        sa.CheckConstraint('used_count BETWEEN 0 AND 3', name='ck_proactive_count'))


def downgrade():
    conn = op.get_bind()
    conn.execute(sa.text('LOCK TABLE conversation, task_outbox, proactive_preference, proactive_daily_counter IN ACCESS EXCLUSIVE MODE'))
    if any(conn.execute(sa.text('SELECT EXISTS (SELECT 1 FROM ' + name + ')')).scalar()
           for name in ('conversation', 'task_outbox', 'proactive_preference', 'proactive_daily_counter')):
        raise RuntimeError('Downgrade requires an empty disposable database')
    op.drop_table('proactive_daily_counter')
    op.drop_table('proactive_preference')
    op.drop_constraint('ck_task_kind', 'task_outbox', type_='check')
    op.create_check_constraint('ck_task_kind', 'task_outbox', "kind IN ('MEMORY_INDEX','MEMORY_CLEANUP','FILE_CLEANUP')")
    op.drop_constraint('ck_conversation_summary_version', 'conversation', type_='check')
    op.drop_column('conversation', 'summary_version')
