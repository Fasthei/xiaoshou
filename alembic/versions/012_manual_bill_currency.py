"""add currency to customer_manual_bill

Revision ID: 012_manual_bill_currency
Revises: 011_allocation_currency
Create Date: 2026-05-18
"""
from alembic import op
import sqlalchemy as sa


revision = "012_manual_bill_currency"
down_revision = "011_allocation_currency"
branch_labels = None
depends_on = None


def upgrade():
    # 添加 currency 字段，默认值为 'USD'
    op.execute(sa.text("""
        ALTER TABLE customer_manual_bill
        ADD COLUMN IF NOT EXISTS currency VARCHAR(10) DEFAULT 'USD'
    """))

    # 为已有记录设置默认值
    op.execute(sa.text("""
        UPDATE customer_manual_bill
        SET currency = 'USD'
        WHERE currency IS NULL
    """))


def downgrade():
    op.execute(sa.text("""
        ALTER TABLE customer_manual_bill
        DROP COLUMN IF EXISTS currency
    """))
