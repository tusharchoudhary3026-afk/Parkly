"""Record driver privacy notice acceptance."""
from alembic import op
import sqlalchemy as sa

revision = "0004_user_consent"
down_revision = "0003_analytics_payments"
branch_labels = None
depends_on = None

def upgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("users")}
    if "consent_at" not in columns:
        op.add_column("users", sa.Column("consent_at", sa.DateTime(timezone=True), nullable=True))
    flag_columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("exception_flags")}
    if "synthetic_label" not in flag_columns:
        op.add_column("exception_flags", sa.Column("synthetic_label", sa.String(length=32), nullable=True))

def downgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("users")}
    if "consent_at" in columns:
        op.drop_column("users", "consent_at")
    flag_columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("exception_flags")}
    if "synthetic_label" in flag_columns:
        op.drop_column("exception_flags", "synthetic_label")
