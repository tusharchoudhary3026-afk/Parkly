"""Add shared location reference data and optional lot location links."""
from alembic import op
import sqlalchemy as sa

revision = "0005_location_hierarchy"
down_revision = "0004_user_consent"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The original 0001 migration uses current Base.metadata.create_all(). A
    # fresh install therefore already has these tables and lot columns before
    # this revision runs; older databases need this migration to create them.
    inspector = sa.inspect(op.get_bind())
    existing_tables = set(inspector.get_table_names())
    location_tables = {
        "location_states",
        "location_cities",
        "location_areas",
        "location_venues",
        "location_suggestions",
    }
    if location_tables.issubset(existing_tables):
        lot_columns = {column["name"] for column in inspector.get_columns("lots")}
        if {"area_id", "venue_id"}.issubset(lot_columns):
            return
        raise RuntimeError("Location tables exist but lot location columns are incomplete")
    if location_tables.intersection(existing_tables):
        raise RuntimeError("Partial location schema found; refusing an unsafe migration")

    op.create_table(
        "location_states",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("code", sa.String(8), nullable=False),
        sa.Column("kind", sa.String(24), nullable=False),
        sa.Column("is_seeded", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.CheckConstraint("kind in ('state', 'union_territory')", name="ck_location_state_kind"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code", name="uq_location_states_code"),
    )
    op.create_index("ux_location_states_lower_name", "location_states", [sa.text("lower(name)")], unique=True)

    op.create_table(
        "location_cities",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("state_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("is_seeded", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("source", sa.String(24), nullable=False, server_default="seed"),
        sa.Column("status", sa.String(24), nullable=False, server_default="active"),
        sa.CheckConstraint("source in ('seed', 'user_submitted')", name="ck_location_city_source"),
        sa.CheckConstraint("status in ('active', 'pending_review')", name="ck_location_city_status"),
        sa.ForeignKeyConstraint(["state_id"], ["location_states.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_location_cities_state_id", "location_cities", ["state_id"])
    op.create_index("ux_location_cities_parent_lower_name", "location_cities", ["state_id", sa.text("lower(name)")], unique=True)

    op.create_table(
        "location_areas",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("city_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("is_seeded", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("source", sa.String(24), nullable=False, server_default="seed"),
        sa.Column("status", sa.String(24), nullable=False, server_default="active"),
        sa.CheckConstraint("source in ('seed', 'user_submitted')", name="ck_location_area_source"),
        sa.CheckConstraint("status in ('active', 'pending_review')", name="ck_location_area_status"),
        sa.ForeignKeyConstraint(["city_id"], ["location_cities.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_location_areas_city_id", "location_areas", ["city_id"])
    op.create_index("ux_location_areas_parent_lower_name", "location_areas", ["city_id", sa.text("lower(name)")], unique=True)

    op.create_table(
        "location_venues",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("area_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("venue_type", sa.String(24), nullable=False),
        sa.Column("is_seeded", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("source", sa.String(24), nullable=False, server_default="seed"),
        sa.Column("status", sa.String(24), nullable=False, server_default="active"),
        sa.Column("data_label", sa.String(24), nullable=False, server_default="SYNTHETIC"),
        sa.Column("latitude", sa.Numeric(9, 6), nullable=True),
        sa.Column("longitude", sa.Numeric(9, 6), nullable=True),
        sa.CheckConstraint("source in ('seed', 'user_submitted')", name="ck_location_venue_source"),
        sa.CheckConstraint("status in ('active', 'pending_review')", name="ck_location_venue_status"),
        sa.CheckConstraint("data_label in ('SYNTHETIC', 'USER_SUBMITTED', 'VERIFIED')", name="ck_location_venue_data_label"),
        sa.CheckConstraint("venue_type in ('mall', 'building', 'market', 'hospital', 'station', 'office', 'other')", name="ck_location_venue_type"),
        sa.ForeignKeyConstraint(["area_id"], ["location_areas.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_location_venues_area_id", "location_venues", ["area_id"])
    op.create_index("ux_location_venues_parent_lower_name", "location_venues", ["area_id", sa.text("lower(name)")], unique=True)

    op.create_table(
        "location_suggestions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("submitted_by_user_id", sa.UUID(), nullable=False),
        sa.Column("state_id", sa.UUID(), nullable=False),
        sa.Column("city_id", sa.UUID(), nullable=True),
        sa.Column("area_id", sa.UUID(), nullable=True),
        sa.Column("target_level", sa.String(12), nullable=False),
        sa.Column("city_name", sa.String(80), nullable=False),
        sa.Column("area_name", sa.String(80), nullable=True),
        sa.Column("venue_name", sa.String(80), nullable=True),
        sa.Column("venue_type", sa.String(24), nullable=True),
        sa.Column("note", sa.String(500), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("reviewed_by", sa.UUID(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("review_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("target_level in ('city', 'area', 'venue')", name="ck_location_suggestion_target_level"),
        sa.CheckConstraint("status in ('pending', 'approved', 'rejected')", name="ck_location_suggestion_status"),
        sa.ForeignKeyConstraint(["submitted_by_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["state_id"], ["location_states.id"]),
        sa.ForeignKeyConstraint(["city_id"], ["location_cities.id"]),
        sa.ForeignKeyConstraint(["area_id"], ["location_areas.id"]),
        sa.ForeignKeyConstraint(["reviewed_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_location_suggestions_submitted_by_user_id", "location_suggestions", ["submitted_by_user_id"])
    op.create_index("ix_location_suggestions_state_id", "location_suggestions", ["state_id"])
    op.create_index("ix_location_suggestions_city_id", "location_suggestions", ["city_id"])
    op.create_index("ix_location_suggestions_area_id", "location_suggestions", ["area_id"])
    op.create_index("ix_location_suggestions_status", "location_suggestions", ["status"])
    op.create_index("ix_location_suggestions_reviewed_by", "location_suggestions", ["reviewed_by"])

    op.add_column("lots", sa.Column("area_id", sa.UUID(), nullable=True))
    op.add_column("lots", sa.Column("venue_id", sa.UUID(), nullable=True))
    op.create_foreign_key("fk_lots_area_id_location_areas", "lots", "location_areas", ["area_id"], ["id"])
    op.create_foreign_key("fk_lots_venue_id_location_venues", "lots", "location_venues", ["venue_id"], ["id"])
    op.create_index("ix_lots_area_id", "lots", ["area_id"])
    op.create_index("ix_lots_venue_id", "lots", ["venue_id"])


def downgrade() -> None:
    op.drop_index("ix_lots_venue_id", table_name="lots")
    op.drop_index("ix_lots_area_id", table_name="lots")
    op.drop_constraint("fk_lots_venue_id_location_venues", "lots", type_="foreignkey")
    op.drop_constraint("fk_lots_area_id_location_areas", "lots", type_="foreignkey")
    op.drop_column("lots", "venue_id")
    op.drop_column("lots", "area_id")
    for name in ("ix_location_suggestions_reviewed_by", "ix_location_suggestions_status",
                 "ix_location_suggestions_area_id", "ix_location_suggestions_city_id",
                 "ix_location_suggestions_state_id", "ix_location_suggestions_submitted_by_user_id"):
        op.drop_index(name, table_name="location_suggestions")
    op.drop_table("location_suggestions")
    op.drop_index("ux_location_venues_parent_lower_name", table_name="location_venues")
    op.drop_index("ix_location_venues_area_id", table_name="location_venues")
    op.drop_table("location_venues")
    op.drop_index("ux_location_areas_parent_lower_name", table_name="location_areas")
    op.drop_index("ix_location_areas_city_id", table_name="location_areas")
    op.drop_table("location_areas")
    op.drop_index("ux_location_cities_parent_lower_name", table_name="location_cities")
    op.drop_index("ix_location_cities_state_id", table_name="location_cities")
    op.drop_table("location_cities")
    op.drop_index("ux_location_states_lower_name", table_name="location_states")
    op.drop_table("location_states")
