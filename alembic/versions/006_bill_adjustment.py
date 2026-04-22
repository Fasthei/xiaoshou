"""bill_adjustment: 账单中心对"订单折扣"的每月覆盖 (discount_rate + surcharge)

Revision ID: 006_bill_adjustment
Revises: 005_insight_cost_guard
Create Date: 2026-04-22

业务背景：
- 销售系统不再用云管 cc_bill 的 original_cost/final_cost 算折扣
  （那是云管侧的成本视角，不给销售看）
- 账单中心新口径：
    原价    = cc_usage.total_cost (客户-货源-当月)
    折扣率  = 最新 approved allocation.discount_rate (该客户-货源)
             * 可被 bill_adjustment 按月覆盖
    折后价  = 原价 × (1 − 折扣率/100) + surcharge (手续费, 可负)
"""
from alembic import op
import sqlalchemy as sa


revision = "006_bill_adjustment"
down_revision = "005_insight_cost_guard"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS bill_adjustment (
            id                     BIGSERIAL     PRIMARY KEY,
            customer_id            BIGINT        NOT NULL,
            resource_id            BIGINT        NOT NULL,
            month                  VARCHAR(7)    NOT NULL,
            discount_rate_override NUMERIC(5, 2),
            surcharge              NUMERIC(15, 2),
            notes                  VARCHAR(500),
            updated_by             VARCHAR(200),
            created_at             TIMESTAMP     DEFAULT CURRENT_TIMESTAMP,
            updated_at             TIMESTAMP     DEFAULT CURRENT_TIMESTAMP
        )
    """))
    op.execute(sa.text(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_bill_adj_cust_res_month "
        "ON bill_adjustment (customer_id, resource_id, month)"
    ))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_bill_adj_customer_month "
        "ON bill_adjustment (customer_id, month)"
    ))


def downgrade():
    op.execute(sa.text("DROP INDEX IF EXISTS ix_bill_adj_customer_month"))
    op.execute(sa.text("DROP INDEX IF EXISTS uq_bill_adj_cust_res_month"))
    op.execute(sa.text("DROP TABLE IF EXISTS bill_adjustment"))
