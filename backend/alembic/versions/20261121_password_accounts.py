"""Add credentials for individual accounts."""

import sqlalchemy as sa
from alembic import op

revision = "20261121_password_accounts"
down_revision = "20261101_operational_readiness"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("user", sa.Column("username", sa.String(32)))
    op.add_column("user", sa.Column("password_hash", sa.Text()))
    op.create_unique_constraint("uq_user_username", "user", ["username"])
    op.create_check_constraint("ck_user_password", "user", "(username IS NULL) = (password_hash IS NULL)")


def downgrade():
    op.drop_constraint("ck_user_password", "user", type_="check")
    op.drop_constraint("uq_user_username", "user", type_="unique")
    op.drop_column("user", "password_hash")
    op.drop_column("user", "username")
