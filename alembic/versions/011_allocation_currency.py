"""allocation.currency 货币列 (ISO 4217, 默认 CNY).

Revision ID: 011_allocation_currency
Revises: 010_customer_manual_bill
Create Date: 2026-05-12
"""
from alembic import op
import sqlalchemy as sa


revision = "011_allocation_currency"
down_revision = "010_customer_manual_bill"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(sa.text(
        "ALTER TABLE IF EXISTS allocation "
        "ADD COLUMN IF NOT EXISTS currency VARCHAR(8) NOT NULL DEFAULT 'CNY'"
    ))


def downgrade():
    op.execute(sa.text("ALTER TABLE IF EXISTS allocation DROP COLUMN IF EXISTS currency"))
