from alembic import op
import sqlalchemy as sa

revision = '20261021_family_messages'
down_revision = '20261019_week7_notifications'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('device_binding', sa.Column('family_id', sa.UUID(), sa.ForeignKey('family.id', ondelete='RESTRICT')))
    op.add_column('device_binding', sa.Column('client_kind', sa.String(24)))
    op.create_check_constraint('ck_device_client_kind', 'device_binding', "client_kind IN ('ELDER_MOBILE','FAMILY_MOBILE')")
    op.create_table('family_message',
        sa.Column('id', sa.UUID(), primary_key=True),
        sa.Column('sequence', sa.BigInteger(), sa.Identity(), nullable=False, unique=True),
        sa.Column('family_id', sa.UUID(), sa.ForeignKey('family.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('sender_user_id', sa.UUID(), sa.ForeignKey('user.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('destination_role', sa.String(16), nullable=False),
        sa.Column('priority', sa.String(16), nullable=False),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("priority IN ('NORMAL','IMPORTANT')", name='ck_message_priority'),
        sa.CheckConstraint('length(text) BETWEEN 1 AND 2000', name='ck_message_text'),
        sa.CheckConstraint("destination_role IN ('ELDER','CHILD','CAREGIVER')", name='ck_message_role'))
    op.create_index('ix_message_family_sequence', 'family_message', ['family_id', 'sequence'])
    op.create_table('message_delivery',
        sa.Column('id', sa.UUID(), primary_key=True),
        sa.Column('message_id', sa.UUID(), sa.ForeignKey('family_message.id', ondelete='CASCADE'), nullable=False),
        sa.Column('recipient_member_id', sa.UUID(), sa.ForeignKey('family_member.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('received_at', sa.DateTime(timezone=True)),
        sa.Column('read_at', sa.DateTime(timezone=True)),
        sa.UniqueConstraint('message_id', 'recipient_member_id', name='uq_delivery_recipient'),
        sa.CheckConstraint('read_at IS NULL OR received_at IS NOT NULL', name='ck_delivery_read_received'))
    op.create_index('ix_delivery_recipient', 'message_delivery', ['recipient_member_id', 'message_id'])


def downgrade():
    conn = op.get_bind()
    conn.execute(sa.text('LOCK TABLE family_message, message_delivery, device_binding IN ACCESS EXCLUSIVE MODE'))
    if conn.execute(sa.text('SELECT EXISTS (SELECT 1 FROM family_message) OR '
                            'EXISTS (SELECT 1 FROM device_binding WHERE family_id IS NOT NULL)')).scalar():
        raise RuntimeError('Downgrade requires an empty disposable database')
    op.drop_table('message_delivery')
    op.drop_table('family_message')
    op.drop_constraint('ck_device_client_kind', 'device_binding', type_='check')
    op.drop_column('device_binding', 'client_kind')
    op.drop_column('device_binding', 'family_id')
