"""customer_manual_bill — 手工录入的过往账单 (区别于云管同步的 cc_bill).

Revision ID: 010_customer_manual_bill
Revises: 009_payment_currency
Create Date: 2026-05-11
"""
from alembic import op
import sqlalchemy as sa


revision = "010_customer_manual_bill"
down_revision = "009_payment_currency"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS customer_manual_bill (
            id          BIGSERIAL PRIMARY KEY,
            customer_id BIGINT NOT NULL REFERENCES customer(id) ON DELETE CASCADE,
            title       VARCHAR(200),
            amount      NUMERIC(15, 2),
            bill_date   DATE,
            notes       TEXT,
            file_url    VARCHAR(500),
            file_name   VARCHAR(200),
            file_size   INTEGER,
            mime_type   VARCHAR(80),
            created_at  TIMESTAMP NOT NULL DEFAULT now(),
            updated_at  TIMESTAMP NOT NULL DEFAULT now()
        )
    """))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_customer_manual_bill_customer "
        "ON customer_manual_bill(customer_id)"
    ))


def downgrade():
    op.execute(sa.text("DROP INDEX IF EXISTS ix_customer_manual_bill_customer"))
    op.execute(sa.text("DROP TABLE IF EXISTS customer_manual_bill"))
