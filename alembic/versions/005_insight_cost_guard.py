"""insight cost guard: add cost_usd and input_hash to customer_insight_run

Revision ID: 005_insight_cost_guard
Revises: 004_v2_lifecycle_columns
Create Date: 2026-04-18

cost_usd  — estimated OpenAI spend for this run (USD, NUMERIC 10,6)
input_hash — sha256 hex of the serialised input (follow-ups + contracts + notes)
             used for 24h cache hit: same customer + same hash + recent run → skip
"""
from alembic import op
import sqlalchemy as sa


revision = "005_insight_cost_guard"
down_revision = "004_v2_lifecycle_columns"
branch_labels = None
depends_on = None


_COLUMNS = [
    ("customer_insight_run", "cost_usd",   "NUMERIC(10,6)"),
    ("customer_insight_run", "input_hash", "VARCHAR(64)"),
]


def upgrade():
    for table, column, col_type in _COLUMNS:
        op.execute(sa.text(
            f"ALTER TABLE IF EXISTS {table} ADD COLUMN IF NOT EXISTS {column} {col_type}"
        ))


def downgrade():
    for table, column, _ in reversed(_COLUMNS):
        op.execute(sa.text(
            f"ALTER TABLE IF EXISTS {table} DROP COLUMN IF EXISTS {column}"
        ))
