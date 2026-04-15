#!/usr/bin/env bash
# Post-deploy smoke test for xiaoshou Container App.
#
# Usage:
#   BASE_URL=https://xiaoshou-api.xxx.eastasia.azurecontainerapps.io ./scripts/smoke-test.sh
#   # or with a real token to also check protected routes:
#   TOKEN=eyJ... BASE_URL=https://...  ./scripts/smoke-test.sh
#
# Exits non-zero on any failure.

set -euo pipefail

BASE_URL="${BASE_URL:?BASE_URL is required (e.g. https://<fqdn>)}"
TOKEN="${TOKEN:-}"

PASS=0
FAIL=0

green() { printf '\033[32m%s\033[0m\n' "$*"; }
red()   { printf '\033[31m%s\033[0m\n' "$*"; }

check() {
  local name="$1"; shift
  local expected_status="$1"; shift
  local url="$1"; shift
  local code
  if [[ $# -gt 0 ]]; then
    code=$(curl -s -o /tmp/smoke.body -w '%{http_code}' "$@" "$url" || true)
  else
    code=$(curl -s -o /tmp/smoke.body -w '%{http_code}' "$url" || true)
  fi
  if [[ "$code" == "$expected_status" ]]; then
    green "  ✓ $name  → $code"
    PASS=$((PASS+1))
  else
    red   "  ✗ $name  → got $code, expected $expected_status"
    red   "    body: $(head -c 200 /tmp/smoke.body)"
    FAIL=$((FAIL+1))
  fi
}

echo "=== Smoke test: $BASE_URL ==="

echo "[1/5] Public endpoints"
check "GET /"        200 "$BASE_URL/"
check "GET /health"  200 "$BASE_URL/health"

echo "[2/5] Docs"
check "GET /docs"    200 "$BASE_URL/docs"

echo "[3/5] Protected without token -> 401"
check "GET /api/customers (no token)" 401 "$BASE_URL/api/customers"
check "GET /api/auth/me    (no token)" 401 "$BASE_URL/api/auth/me"

echo "[4/5] Auth redirect flow"
check "GET /api/auth/login -> 302/307" 307 "$BASE_URL/api/auth/login" -o /dev/null

if [[ -n "$TOKEN" ]]; then
  echo "[5/5] Protected with token"
  check "GET /api/auth/me  (token)" 200 "$BASE_URL/api/auth/me" -H "Authorization: Bearer $TOKEN"
  check "GET /api/customers (token)" 200 "$BASE_URL/api/customers?page=1" -H "Authorization: Bearer $TOKEN"
else
  echo "[5/5] Protected-with-token checks skipped (set TOKEN=... to run)"
fi

echo
echo "Pass: $PASS   Fail: $FAIL"
[[ "$FAIL" -eq 0 ]]
