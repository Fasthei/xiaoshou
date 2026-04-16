-- ================================================================
-- Backfill: 把所有历史 gongdan/工单关联客户回填为 customer_status='formal'
-- 安全协议: BEGIN -> 预览 -> UPDATE -> 核对条数 -> COMMIT (或 ROLLBACK)
-- 使用:
--   psql "$DATABASE_URL" -f scripts/backfill_formal_status.sql
-- 或在 Azure Container Apps 容器内:
--   DATABASE_URL=$(az containerapp show ... --query properties...)
-- ================================================================
BEGIN;

-- Step 1: 预览待回填的客户 (确认条数合理再跑 UPDATE)
SELECT
    customer_code,
    customer_name,
    customer_status,
    source_system
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
ORDER BY customer_code;

-- Step 2: 统计条数 (期望 ~18)
SELECT COUNT(*) AS total_to_update
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
  );

-- Step 3: 执行 UPDATE
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
  );

-- Step 4: 核对
SELECT COUNT(*) AS formal_total
FROM customer
WHERE is_deleted = FALSE AND customer_status = 'formal';

-- Step 5: 看一眼结果
SELECT customer_code, customer_name, customer_status, source_system
FROM customer
WHERE customer_status = 'formal' AND is_deleted = FALSE
ORDER BY customer_code;

-- 如条数符合预期 -> COMMIT;  否则 -> ROLLBACK;
COMMIT;
