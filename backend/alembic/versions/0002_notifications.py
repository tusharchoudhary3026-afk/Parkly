"""Persist driver-facing in-app notices."""
from alembic import op
from app.models import Notification

revision = "0002_notifications"
down_revision = "0001_initial"
branch_labels = None
depends_on = None

def upgrade() -> None:
    Notification.__table__.create(bind=op.get_bind(), checkfirst=True)

def downgrade() -> None:
    Notification.__table__.drop(bind=op.get_bind(), checkfirst=True)
