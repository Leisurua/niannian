from alembic import op
import sqlalchemy as sa

revision = '20261023_attention_contacts'
down_revision = '20261021_family_messages'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('notification', sa.Column('provider_status', sa.String(24)))
    op.drop_constraint('ck_notification_preference_channels', 'notification_preference', type_='check')
    op.create_check_constraint('ck_notification_preference_channels', 'notification_preference',
        "jsonb_typeof(channels) = 'array' AND channels <@ '[\"IN_APP\",\"PUSH\",\"SMS\",\"PHONE\"]'::jsonb")
    op.create_table('family_contact',
        sa.Column('id', sa.UUID(), primary_key=True),
        sa.Column('family_id', sa.UUID(), sa.ForeignKey('family.id', ondelete='CASCADE'), nullable=False),
        sa.Column('user_id', sa.UUID(), sa.ForeignKey('user.id', ondelete='CASCADE'), nullable=False),
        sa.Column('phone_ciphertext', sa.Text()), sa.Column('topic_ciphertext', sa.Text()),
        sa.Column('share_phone', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('emergency', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('version', sa.Integer(), server_default='1', nullable=False),
        sa.UniqueConstraint('family_id', 'user_id', name='uq_family_contact_member'),
        sa.CheckConstraint('version > 0', name='ck_family_contact_version'))


def downgrade():
    conn = op.get_bind()
    conn.execute(sa.text('LOCK TABLE family_contact, notification_preference IN ACCESS EXCLUSIVE MODE'))
    if conn.execute(sa.text("SELECT EXISTS (SELECT 1 FROM family_contact) OR EXISTS "
            "(SELECT 1 FROM notification_preference WHERE NOT channels <@ '[\"IN_APP\",\"PUSH\"]'::jsonb)")).scalar():
        raise RuntimeError('Downgrade requires no contacts or external channel preferences')
    op.drop_table('family_contact')
    op.drop_column('notification', 'provider_status')
    op.drop_constraint('ck_notification_preference_channels', 'notification_preference', type_='check')
    op.create_check_constraint('ck_notification_preference_channels', 'notification_preference',
        "jsonb_typeof(channels) = 'array' AND channels <@ '[\"IN_APP\",\"PUSH\"]'::jsonb")
