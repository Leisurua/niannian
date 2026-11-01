"""Record report topic classification provenance without retaining source text."""
from alembic import op
import sqlalchemy as sa

revision = '20261101_report_semantics'
down_revision = '20261101_elder_help_requests'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('interaction_metric', sa.Column('topic_method', sa.String(16), nullable=False, server_default='RULE'))
    op.add_column('interaction_metric', sa.Column('topic_model_version', sa.String(64), nullable=True))
    op.create_check_constraint('ck_metric_topic_method', 'interaction_metric',
        "topic_method IN ('RULE','LOCAL_SEMANTIC','RULE_FALLBACK')")


def downgrade():
    op.drop_constraint('ck_metric_topic_method', 'interaction_metric', type_='check')
    op.drop_column('interaction_metric', 'topic_model_version')
    op.drop_column('interaction_metric', 'topic_method')
