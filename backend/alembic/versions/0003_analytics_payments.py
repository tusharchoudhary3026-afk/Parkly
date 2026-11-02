"""Add snapshots, tariff revisions, test payments, and explicit penalty decisions."""
from alembic import op
from app.models import OccupancySnapshot, Payment, PenaltyDecision, TariffVersion

revision = "0003_analytics_payments"
down_revision = "0002_notifications"
branch_labels = None
depends_on = None

def upgrade() -> None:
    bind = op.get_bind()
    for model in (OccupancySnapshot, TariffVersion, Payment, PenaltyDecision):
        model.__table__.create(bind=bind, checkfirst=True)
    op.execute("""
      CREATE OR REPLACE FUNCTION reject_audit_mutation() RETURNS trigger AS $$
      BEGIN RAISE EXCEPTION 'audit_logs is append-only'; END;
      $$ LANGUAGE plpgsql
    """)
    op.execute("DROP TRIGGER IF EXISTS audit_logs_append_only ON audit_logs")
    op.execute("""
      CREATE TRIGGER audit_logs_append_only BEFORE UPDATE OR DELETE ON audit_logs
      FOR EACH ROW EXECUTE FUNCTION reject_audit_mutation()
    """)

def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS audit_logs_append_only ON audit_logs")
    op.execute("DROP FUNCTION IF EXISTS reject_audit_mutation()")
    bind = op.get_bind()
    for model in (PenaltyDecision, Payment, TariffVersion, OccupancySnapshot):
        model.__table__.drop(bind=bind, checkfirst=True)
