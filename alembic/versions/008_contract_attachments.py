"""contract attachments — multi-file per contract.

Revision ID: 008_contract_attachments
Revises: 007_customer_lifecycle_tombstone
Create Date: 2026-05-09

变更：
1. 新建 contract_attachment 表 (一对多, 一个合同挂多份文件)
2. 把现有 contract.file_url 行回填到 contract_attachment (旧的"主附件"成为
   该合同的第一条 attachment)
3. 删掉 contract 表上的 file_url / file_name / file_size / mime_type 列
   (单一来源, 避免两套真值)
"""
from alembic import op
import sqlalchemy as sa


revision = "008_contract_attachments"
down_revision = "007_customer_lifecycle_tombstone"
branch_labels = None
depends_on = None


def upgrade():
    # 1. 建表
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS contract_attachment (
            id          BIGSERIAL PRIMARY KEY,
            contract_id BIGINT NOT NULL REFERENCES contract(id) ON DELETE CASCADE,
            file_url    VARCHAR(500) NOT NULL,
            file_name   VARCHAR(200),
            file_size   INTEGER,
            mime_type   VARCHAR(80),
            created_at  TIMESTAMP NOT NULL DEFAULT now()
        )
    """))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_contract_attachment_contract "
        "ON contract_attachment(contract_id)"
    ))

    # 2. 回填: contract.file_url 非空的 → contract_attachment 一行
    op.execute(sa.text("""
        INSERT INTO contract_attachment
            (contract_id, file_url, file_name, file_size, mime_type, created_at)
        SELECT
            id, file_url, file_name, file_size, mime_type, COALESCE(created_at, now())
        FROM contract
        WHERE file_url IS NOT NULL
    """))

    # 3. 删旧列
    for col in ("file_url", "file_name", "file_size", "mime_type"):
        op.execute(sa.text(
            f"ALTER TABLE IF EXISTS contract DROP COLUMN IF EXISTS {col}"
        ))


def downgrade():
    # 加回旧列
    op.execute(sa.text("ALTER TABLE contract ADD COLUMN IF NOT EXISTS file_url   VARCHAR(500)"))
    op.execute(sa.text("ALTER TABLE contract ADD COLUMN IF NOT EXISTS file_name  VARCHAR(200)"))
    op.execute(sa.text("ALTER TABLE contract ADD COLUMN IF NOT EXISTS file_size  INTEGER"))
    op.execute(sa.text("ALTER TABLE contract ADD COLUMN IF NOT EXISTS mime_type  VARCHAR(80)"))

    # 把每个合同最早的 attachment 回写到 contract.file_url
    op.execute(sa.text("""
        UPDATE contract c SET
            file_url  = a.file_url,
            file_name = a.file_name,
            file_size = a.file_size,
            mime_type = a.mime_type
        FROM (
            SELECT DISTINCT ON (contract_id)
                contract_id, file_url, file_name, file_size, mime_type
            FROM contract_attachment
            ORDER BY contract_id, created_at ASC
        ) a
        WHERE c.id = a.contract_id
    """))

    op.execute(sa.text("DROP INDEX IF EXISTS ix_contract_attachment_contract"))
    op.execute(sa.text("DROP TABLE IF EXISTS contract_attachment"))
