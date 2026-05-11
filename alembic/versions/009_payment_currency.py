"""payment.currency 货币列 (ISO 4217, 默认 CNY).

Revision ID: 009_payment_currency
Revises: 008_contract_attachments
Create Date: 2026-05-11
"""
from alembic import op
import sqlalchemy as sa


revision = "009_payment_currency"
down_revision = "008_contract_attachments"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(sa.text(
        "ALTER TABLE IF EXISTS payment "
        "ADD COLUMN IF NOT EXISTS currency VARCHAR(8) NOT NULL DEFAULT 'CNY'"
    ))


def downgrade():
    op.execute(sa.text("ALTER TABLE IF EXISTS payment DROP COLUMN IF EXISTS currency"))
