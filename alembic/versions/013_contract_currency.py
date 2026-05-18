"""add currency to contract

Revision ID: 013_contract_currency
Revises: 012_manual_bill_currency
Create Date: 2026-05-18
"""
from alembic import op
import sqlalchemy as sa


revision = "013_contract_currency"
down_revision = "012_manual_bill_currency"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(sa.text("""
        ALTER TABLE contract
        ADD COLUMN IF NOT EXISTS currency VARCHAR(10) DEFAULT 'USD'
    """))
    op.execute(sa.text("""
        UPDATE contract SET currency = 'USD' WHERE currency IS NULL
    """))


def downgrade():
    op.execute(sa.text("""
        ALTER TABLE contract DROP COLUMN IF EXISTS currency
    """))
