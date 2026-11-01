"""Persist elder help-request delivery failures."""
from alembic import op
import sqlalchemy as sa

revision = '20261101_elder_help_requests'
down_revision = '20261029_family_voices'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('signal_event', sa.Column('failure_code', sa.String(64)))


def downgrade():
    op.drop_column('signal_event', 'failure_code')
