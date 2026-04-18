"""allow manual customers without customer_code

Revision ID: 003_customer_code_nullable
Revises: 002_formal_backfill
Create Date: 2026-04-18
"""
from alembic import op
import sqlalchemy as sa


revision = "003_customer_code_nullable"
down_revision = "002_formal_backfill"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column("customer", "customer_code", existing_type=sa.String(length=50), nullable=True)
    op.alter_column("customer", "customer_status", existing_type=sa.String(length=20), type_=sa.String(length=32), nullable=False)


def downgrade():
    bind = op.get_bind()
    bind.execute(sa.text(
        """
        UPDATE customer
        SET customer_code = CONCAT('LEGACY-', id)
        WHERE customer_code IS NULL
        """
    ))
    bind.execute(sa.text(
        """
        UPDATE customer
        SET customer_status = 'active'
        WHERE customer_status = 'pending_formalization'
        """
    ))
    op.alter_column("customer", "customer_status", existing_type=sa.String(length=32), type_=sa.String(length=20), nullable=False)
    op.alter_column("customer", "customer_code", existing_type=sa.String(length=50), nullable=False)
