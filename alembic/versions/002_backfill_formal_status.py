"""backfill customer_status='formal' for gongdan/ticket-linked customers

Revision ID: 002_formal_backfill
Revises: 001
Create Date: 2026-04-16

Rationale:
  规则变更 — 走 gongdan 工单同步过来的客户 = formal (正式客户)。
  formal 为系统终态, 用户不能手动设置或修改 (由 API + 前端约束)。
  本迁移将现有:
    1) source_system = 'gongdan' 的客户
    2) 在 ticket 表里出现过 customer_code 的客户
  统一回填为 customer_status = 'formal' (前提: 当前不是 formal)。
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "002_formal_backfill"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()

    # 先打印预览 (migration 日志里可见), 方便审计条数
    preview_sql = sa.text(
        """
        SELECT COUNT(*) AS n
        FROM customer
        WHERE is_deleted = FALSE
          AND customer_status <> 'formal'
          AND (
              source_system = 'gongdan'
              OR customer_code IN (
                  SELECT DISTINCT customer_code
                  FROM ticket
                  WHERE customer_code IS NOT NULL
              )
          )
        """
    )
    # ticket 表如果还不存在 (比如新环境), 降级到只看 source_system
    fallback_sql = sa.text(
        """
        SELECT COUNT(*) AS n
        FROM customer
        WHERE is_deleted = FALSE
          AND customer_status <> 'formal'
          AND source_system = 'gongdan'
        """
    )

    has_ticket = bind.execute(sa.text(
        "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name='ticket')"
    )).scalar()

    if has_ticket:
        n = bind.execute(preview_sql).scalar() or 0
        print(f"[002_formal_backfill] 即将回填 formal 的客户数: {n}")
        op.execute(
            """
            UPDATE customer
            SET customer_status = 'formal',
                updated_at = now()
            WHERE is_deleted = FALSE
              AND customer_status <> 'formal'
              AND (
                  source_system = 'gongdan'
                  OR customer_code IN (
                      SELECT DISTINCT customer_code
                      FROM ticket
                      WHERE customer_code IS NOT NULL
                  )
              )
            """
        )
    else:
        n = bind.execute(fallback_sql).scalar() or 0
        print(f"[002_formal_backfill] (无 ticket 表) 即将回填 formal 的客户数: {n}")
        op.execute(
            """
            UPDATE customer
            SET customer_status = 'formal',
                updated_at = now()
            WHERE is_deleted = FALSE
              AND customer_status <> 'formal'
              AND source_system = 'gongdan'
            """
        )


def downgrade():
    # 回滚: 将 source_system='gongdan' 的 formal 客户改回 active
    # (手工 formal 的场景不存在, 因为 API 不允许)
    op.execute(
        """
        UPDATE customer
        SET customer_status = 'active',
            updated_at = now()
        WHERE is_deleted = FALSE
          AND customer_status = 'formal'
          AND source_system = 'gongdan'
        """
    )
