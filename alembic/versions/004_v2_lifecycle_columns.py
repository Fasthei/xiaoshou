"""v2 lifecycle: allocation discount/approval, follow_up threading, sales_user yearly targets

Revision ID: 004_v2_lifecycle_columns
Revises: 003_customer_code_nullable
Create Date: 2026-04-18

补齐 v2 业务流程重构期间引入但未落生产 DB 的列。本地已通过手动 ALTER 验证。
"""
from alembic import op
import sqlalchemy as sa


revision = "004_v2_lifecycle_columns"
down_revision = "003_customer_code_nullable"
branch_labels = None
depends_on = None


# 直接用 PG 原生 ALTER TABLE IF EXISTS ... ADD COLUMN IF NOT EXISTS (PG 9.6+):
# - 表不存在: 整条 ALTER 跳过 (兼容 fresh DB 时 SQLAlchemy create_all 还没跑过的场景)
# - 列已存在: ADD 跳过 (兼容本地手 ALTER 后跑迁移的场景)
# 完全幂等, 不依赖 inspector 缓存。

_COLUMNS = [
    ("allocation",          "discount_rate",             "NUMERIC(5,2)"),
    ("allocation",          "unit_price_after_discount", "NUMERIC(15,2)"),
    ("customer_follow_up",  "to_sales_user_id",          "BIGINT"),
    ("customer_follow_up",  "parent_follow_up_id",       "BIGINT"),
    ("sales_user",          "annual_sales_target",       "NUMERIC(15,2)"),
    ("sales_user",          "annual_profit_target",      "NUMERIC(15,2)"),
    ("sales_user",          "profit_margin_target",      "NUMERIC(5,2)"),
]


def upgrade():
    for table, column, col_type in _COLUMNS:
        op.execute(sa.text(
            f"ALTER TABLE IF EXISTS {table} ADD COLUMN IF NOT EXISTS {column} {col_type}"
        ))

    # 数据迁移: 老 lifecycle_stage 收编到 contacting
    # 包 DO block 防 lifecycle_stage 列不存在 (fresh DB 走 alembic 时, v2 列由 main.lifespan 的 create_all 补)
    op.execute(sa.text("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'customer' AND column_name = 'lifecycle_stage'
            ) THEN
                UPDATE customer
                SET lifecycle_stage = 'contacting'
                WHERE lifecycle_stage IN ('order_pending', 'order_approved');
            END IF;
        END $$;
    """))


def downgrade():
    # 反向 DROP COLUMN IF EXISTS (反序), 不还原数据迁移 (无安全可逆做法)。
    for table, column, _ in reversed(_COLUMNS):
        op.execute(sa.text(
            f"ALTER TABLE IF EXISTS {table} DROP COLUMN IF EXISTS {column}"
        ))
