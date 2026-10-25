from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '20261024_interaction_stats'
down_revision = '20261023_attention_contacts'
branch_labels = None
depends_on = None

OLD_SCOPES = "'VOICE','PORTRAIT','FAMILY_MEMORY','HEALTH_MEDICATION','CONVERSATION_SUMMARY','CAMERA_PROXIMITY','NOTIFICATION_TO_FAMILY'"


def upgrade():
    op.drop_constraint('ck_consent_scope', 'consent', type_='check')
    op.create_check_constraint('ck_consent_scope', 'consent', f"scope IN ({OLD_SCOPES},'INTERACTION_STATS')")
    op.create_table('interaction_metric',
        sa.Column('conversation_id', sa.UUID(), sa.ForeignKey('conversation.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('sequence', sa.Integer(), primary_key=True),
        sa.Column('family_id', sa.UUID(), sa.ForeignKey('family.id', ondelete='CASCADE'), nullable=False),
        sa.Column('owner_user_id', sa.UUID(), sa.ForeignKey('user.id', ondelete='CASCADE'), nullable=False),
        sa.Column('consent_id', sa.UUID(), sa.ForeignKey('consent.id', ondelete='CASCADE'), nullable=False),
        sa.Column('occurred_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('duration_seconds', sa.Integer(), nullable=False),
        sa.Column('emotions', postgresql.ARRAY(sa.String(24)), nullable=False),
        sa.Column('topics', postgresql.ARRAY(sa.String(24)), nullable=False),
        sa.Column('simulated', sa.Boolean(), nullable=False),
        sa.Column('retention_until', sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint('sequence > 0 AND duration_seconds BETWEEN 0 AND 300', name='ck_metric_duration'),
        sa.CheckConstraint('retention_until > occurred_at', name='ck_metric_retention'))
    op.create_index('ix_metric_family_owner_time', 'interaction_metric', ['family_id', 'owner_user_id', 'occurred_at'])


def downgrade():
    conn = op.get_bind()
    conn.execute(sa.text('LOCK TABLE interaction_metric, consent IN ACCESS EXCLUSIVE MODE'))
    if conn.execute(sa.text("SELECT EXISTS (SELECT 1 FROM interaction_metric) OR EXISTS (SELECT 1 FROM consent WHERE scope='INTERACTION_STATS')")).scalar():
        raise RuntimeError('Downgrade requires no interaction statistics or statistics consent history')
    op.drop_table('interaction_metric')
    op.drop_constraint('ck_consent_scope', 'consent', type_='check')
    op.create_check_constraint('ck_consent_scope', 'consent', f'scope IN ({OLD_SCOPES})')
