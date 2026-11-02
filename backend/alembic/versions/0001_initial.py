"""Initial tenant-scoped smart parking schema."""
from alembic import op
from app.models import Base

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")
    Base.metadata.create_all(bind=op.get_bind())
    op.execute("""ALTER TABLE bookings ADD CONSTRAINT booking_no_overlapping_slot_windows
      EXCLUDE USING gist (slot_id WITH =, tstzrange(starts_at, ends_at, '[)') WITH &&)
      WHERE (status IN ('held', 'confirmed', 'checked_in'))""")

def downgrade() -> None:
    op.execute("ALTER TABLE bookings DROP CONSTRAINT IF EXISTS booking_no_overlapping_slot_windows")
    Base.metadata.drop_all(bind=op.get_bind())
