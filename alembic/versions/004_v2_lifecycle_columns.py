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


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    cols = [c["name"] for c in insp.get_columns(table)]
    return column in cols


def upgrade():
    # allocation: 折扣 + 折后单价
    if not _has_column("allocation", "discount_rate"):
        op.add_column("allocation",
            sa.Column("discount_rate", sa.Numeric(5, 2), nullable=True, comment="折扣率 % (可负表示加价)"))
    if not _has_column("allocation", "unit_price_after_discount"):
        op.add_column("allocation",
            sa.Column("unit_price_after_discount", sa.Numeric(15, 2), nullable=True, comment="折后单价"))

    # customer_follow_up: 收件人 + 回复线程
    if not _has_column("customer_follow_up", "to_sales_user_id"):
        op.add_column("customer_follow_up",
            sa.Column("to_sales_user_id", sa.BigInteger(), nullable=True, comment="收件销售 ID (留言/转分配用)"))
    if not _has_column("customer_follow_up", "parent_follow_up_id"):
        op.add_column("customer_follow_up",
            sa.Column("parent_follow_up_id", sa.BigInteger(), nullable=True, comment="父跟进 ID (回复线程)"))

    # sales_user: 年度三目标
    if not _has_column("sales_user", "annual_sales_target"):
        op.add_column("sales_user",
            sa.Column("annual_sales_target", sa.Numeric(15, 2), nullable=True, comment="年度销售额目标"))
    if not _has_column("sales_user", "annual_profit_target"):
        op.add_column("sales_user",
            sa.Column("annual_profit_target", sa.Numeric(15, 2), nullable=True, comment="年度毛利目标"))
    if not _has_column("sales_user", "profit_margin_target"):
        op.add_column("sales_user",
            sa.Column("profit_margin_target", sa.Numeric(5, 2), nullable=True, comment="年度毛利率目标"))

    # 数据迁移: 老 lifecycle_stage 收编到 contacting
    op.execute("""
        UPDATE customer
        SET lifecycle_stage = 'contacting'
        WHERE lifecycle_stage IN ('order_pending', 'order_approved')
    """)


def downgrade():
    # 反向 drop. 不还原数据迁移 (无安全可逆做法)。
    for table, col in [
        ("sales_user", "profit_margin_target"),
        ("sales_user", "annual_profit_target"),
        ("sales_user", "annual_sales_target"),
        ("customer_follow_up", "parent_follow_up_id"),
        ("customer_follow_up", "to_sales_user_id"),
        ("allocation", "unit_price_after_discount"),
        ("allocation", "discount_rate"),
    ]:
        if _has_column(table, col):
            op.drop_column(table, col)
