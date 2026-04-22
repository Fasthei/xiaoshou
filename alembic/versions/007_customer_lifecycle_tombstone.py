"""customer lifecycle tombstone + resource soft delete tracking.

Revision ID: 007_customer_lifecycle_tombstone
Revises: 006_bill_adjustment
Create Date: 2026-04-22

议题 B 两级删除策略：
  1. 工单同步后发现上游已消失的正式客户 → 本地降级为 lead (is_deleted 保持 false)
     demoted_at / demoted_reason 记录来龙去脉
  2. 销售在商机池里手动"彻底删" → is_deleted=true + deleted_at / deleted_by /
     deletion_reason 档案可查，但列表不显示
     这条墓碑用于拦截工单同名复活（source_system='gongdan' AND customer_code 命中）
  3. 货源类似：云管同步发现上游消失 → is_deleted=true + deleted_at，保留 customer_resource
"""
from alembic import op
import sqlalchemy as sa


revision = "007_customer_lifecycle_tombstone"
down_revision = "006_bill_adjustment"
branch_labels = None
depends_on = None


_CUSTOMER_COLS = [
    ("demoted_at",      "TIMESTAMP"),
    ("demoted_reason",  "VARCHAR(200)"),
    ("deleted_at",      "TIMESTAMP"),
    ("deleted_by",      "VARCHAR(200)"),
    ("deletion_reason", "VARCHAR(200)"),
]

_RESOURCE_COLS = [
    ("deleted_at", "TIMESTAMP"),
]


def upgrade():
    for col, tp in _CUSTOMER_COLS:
        op.execute(sa.text(
            f"ALTER TABLE IF EXISTS customer ADD COLUMN IF NOT EXISTS {col} {tp}"
        ))
    for col, tp in _RESOURCE_COLS:
        op.execute(sa.text(
            f"ALTER TABLE IF EXISTS resource ADD COLUMN IF NOT EXISTS {col} {tp}"
        ))


def downgrade():
    for col, _ in reversed(_RESOURCE_COLS):
        op.execute(sa.text(f"ALTER TABLE IF EXISTS resource DROP COLUMN IF EXISTS {col}"))
    for col, _ in reversed(_CUSTOMER_COLS):
        op.execute(sa.text(f"ALTER TABLE IF EXISTS customer DROP COLUMN IF EXISTS {col}"))
