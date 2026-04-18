#!/usr/bin/env bash
# 从云上 Azure PostgreSQL 同步数据到本地 docker postgres 容器。
# 前置: az login + 本机公网 IP 加入 dataope 防火墙 + docker compose up -d 已跑。
# 用法: bash scripts/sync_from_prod.sh
set -euo pipefail

PROD_HOST="${PROD_HOST:-dataope.postgres.database.azure.com}"
PROD_USER="${PROD_USER:-azuredb}"
PROD_DB="${PROD_DB:-sales_system}"
LOCAL_CONTAINER="${LOCAL_CONTAINER:-xiaoshou-postgres-1}"
LOCAL_USER="${LOCAL_USER:-sales}"
LOCAL_DB="${LOCAL_DB:-sales_system}"
DUMP_FILE="${DUMP_FILE:-/tmp/xs-prod-dump.sql}"

echo "[1/4] 拿云端 PG 密码..."
PG_PW=$(az containerapp secret show -g sales-rg -n xiaoshou-api --secret-name pg-password --query value -o tsv)

echo "[2/4] pg_dump 云端 → $DUMP_FILE (用 docker postgres:18-alpine 客户端)..."
docker run --rm -e PGPASSWORD="$PG_PW" postgres:18-alpine \
  pg_dump -h "$PROD_HOST" -U "$PROD_USER" -d "$PROD_DB" \
  --no-owner --no-acl --clean --if-exists -F p > "$DUMP_FILE"
echo "  dump size: $(du -h "$DUMP_FILE" | cut -f1)"

echo "[3/4] 导入本地 $LOCAL_CONTAINER..."
docker exec -i "$LOCAL_CONTAINER" psql -U "$LOCAL_USER" -d "$LOCAL_DB" < "$DUMP_FILE" \
  > /tmp/xs-restore.log 2>&1 || true
echo "  errors: $(grep -cE '^(ERROR|FATAL)' /tmp/xs-restore.log || true)"

echo "[4/4] 验证关键表行数..."
for t in customer allocation customer_resource customer_follow_up sales_user resource; do
  cnt=$(docker exec "$LOCAL_CONTAINER" psql -U "$LOCAL_USER" -d "$LOCAL_DB" -t -A -c "SELECT count(*) FROM $t" 2>/dev/null || echo "?")
  printf "  %-25s %s\n" "$t" "$cnt"
done

echo "完成。重启 api 让连接池刷新: docker compose restart api"
