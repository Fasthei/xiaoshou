#!/usr/bin/env bash
# Post-deploy smoke test for xiaoshou Container App.
#
# Usage:
#   BASE_URL=https://xiaoshou-api.xxx.eastasia.azurecontainerapps.io ./scripts/smoke-test.sh
#   # or with a real token to also check protected routes:
#   TOKEN=eyJ... BASE_URL=https://...  ./scripts/smoke-test.sh
#
# Exits non-zero on any failure.
#
# "Acceptable 502" policy (applied only to cloudcost-dependent routes,
# i.e. /api/bridge/* and /api/trend/*):
#   200                              → pass
#   502 + JSON body, detail 含 "云管" 或 "cloudcost"
#                                    → pass (upstream cloudcost is down,
#                                    but xiaoshou produced the expected
#                                    friendly error envelope — both the
#                                    current "cloudcost ... 查询失败" and
#                                    the unified "云管 ... 查询失败"
#                                    variants are accepted).
#   anything else                    → fail

set -euo pipefail

BASE_URL="${BASE_URL:?BASE_URL is required (e.g. https://<fqdn>)}"
TOKEN="${TOKEN:-}"

PASS=0
FAIL=0

green()  { printf '\033[32m%s\033[0m\n' "$*"; }
yellow() { printf '\033[33m%s\033[0m\n' "$*"; }
red()    { printf '\033[31m%s\033[0m\n' "$*"; }

# ---------------------------------------------------------------------------
# check NAME EXPECTED_STATUS URL [curl args...]
# Expects the exact HTTP status.
# ---------------------------------------------------------------------------
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
    green "  ok  $name  -> $code"
    PASS=$((PASS+1))
  else
    red   "  FAIL  $name  -> got $code, expected $expected_status"
    red   "    body: $(head -c 200 /tmp/smoke.body)"
    FAIL=$((FAIL+1))
  fi
}

# ---------------------------------------------------------------------------
# check_bridge NAME URL [curl args...]
# For /api/bridge/* and /api/trend/* endpoints:
#   - 200 passes
#   - 502 with JSON body whose detail mentions "云管" passes (it's the
#     documented friendly-error envelope from the bridge layer).
#   - Everything else fails.
# ---------------------------------------------------------------------------
check_bridge() {
  local name="$1"; shift
  local url="$1"; shift
  local code
  if [[ $# -gt 0 ]]; then
    code=$(curl -s -o /tmp/smoke.body -w '%{http_code}' "$@" "$url" || true)
  else
    code=$(curl -s -o /tmp/smoke.body -w '%{http_code}' "$url" || true)
  fi
  if [[ "$code" == "200" ]]; then
    green "  ok  $name  -> 200"
    PASS=$((PASS+1))
    return
  fi
  if [[ "$code" == "502" ]]; then
    # Accept if the body is JSON and the detail field (anywhere in the first
    # 500 chars) mentions 云管 — that is the contract with the frontend.
    local body
    body=$(head -c 500 /tmp/smoke.body || true)
    if printf '%s' "$body" | python3 -c '
import json,sys
raw = sys.stdin.read()
try:
    obj = json.loads(raw)
except Exception:
    sys.exit(2)
detail = str(obj.get("detail", "")).lower()
# Accept both the current "cloudcost ... 查询失败" envelope and the future
# unified "云管 ... 查询失败" envelope. Either signals "we talked to
# cloudcost and it rejected/timed out" — which is a known, monitored,
# non-xiaoshou-fault state we want the frontend to display gracefully.
ok = ("云管" in detail) or ("cloudcost" in detail)
sys.exit(0 if ok else 3)
' 2>/dev/null; then
      yellow "  ok  $name  -> 502 (acceptable: cloudcost upstream down, friendly envelope)"
      PASS=$((PASS+1))
      return
    fi
    red "  FAIL  $name  -> 502 but body is not the expected {detail: '云管|cloudcost ...'} envelope"
    red "    body: $body"
    FAIL=$((FAIL+1))
    return
  fi
  red "  FAIL  $name  -> got $code, expected 200 or acceptable-502"
  red "    body: $(head -c 200 /tmp/smoke.body)"
  FAIL=$((FAIL+1))
}

echo "=== Smoke test: $BASE_URL ==="

echo "[1/7] Public endpoints"
check "GET /"        200 "$BASE_URL/"
check "GET /health"  200 "$BASE_URL/health"

echo "[2/7] Docs"
check "GET /docs"    200 "$BASE_URL/docs"

echo "[3/7] Protected without token -> 401"
check "GET /api/customers (no token)" 401 "$BASE_URL/api/customers"
check "GET /api/auth/me    (no token)" 401 "$BASE_URL/api/auth/me"

echo "[4/7] Auth redirect flow"
check "GET /api/auth/login -> 307" 307 "$BASE_URL/api/auth/login" -o /dev/null

if [[ -z "$TOKEN" ]]; then
  echo "[5-7/7] Token-backed checks skipped (set TOKEN=... to run)"
  echo
  echo "Pass: $PASS   Fail: $FAIL"
  [[ "$FAIL" -eq 0 ]]
  exit $?
fi

MONTH="$(date +%Y-%m)"

echo "[5/7] Protected core (with token)"
check "GET /api/auth/me"                      200 "$BASE_URL/api/auth/me" \
  -H "Authorization: Bearer $TOKEN"
check "GET /api/customers?page_size=1"        200 "$BASE_URL/api/customers?page_size=1" \
  -H "Authorization: Bearer $TOKEN"

echo "[6/7] Sales + enrich (with token)"
check "GET /api/sales/users?active_only=false" 200 "$BASE_URL/api/sales/users?active_only=false" \
  -H "Authorization: Bearer $TOKEN"
check "GET /api/sales/rules?active_only=false" 200 "$BASE_URL/api/sales/rules?active_only=false" \
  -H "Authorization: Bearer $TOKEN"
check "GET /api/enrich/leads?q=新能源&num=3"    200 "$BASE_URL/api/enrich/leads?q=%E6%96%B0%E8%83%BD%E6%BA%90&num=3" \
  -H "Authorization: Bearer $TOKEN"

echo "[7/9] Cloudcost bridge (200 or acceptable 502)"
check_bridge "GET /api/bridge/alerts?month=$MONTH" \
  "$BASE_URL/api/bridge/alerts?month=$MONTH" \
  -H "Authorization: Bearer $TOKEN"
check_bridge "GET /api/bridge/bills?month=$MONTH&page_size=5" \
  "$BASE_URL/api/bridge/bills?month=$MONTH&page_size=5" \
  -H "Authorization: Bearer $TOKEN"
check_bridge "GET /api/trend/daily?days=7" \
  "$BASE_URL/api/trend/daily?days=7" \
  -H "Authorization: Bearer $TOKEN"

# ---------------------------------------------------------------------------
# [8/9] Briefing + customer health/timeline  (added by Team C — post Bug-A/B fix)
#
# These routes compose data from sales/customers/enrich and — for /timeline —
# depend on sales_user soft-delete working (Bug A). If /api/sales/users
# crashes on FK after an admin hard-delete, /api/customers/:id/timeline
# would also 500. A green run here is part of the post-fix contract.
# ---------------------------------------------------------------------------
echo "[8/9] Briefing & customer 360"
check "GET /api/briefing" 200 \
  "$BASE_URL/api/briefing" \
  -H "Authorization: Bearer $TOKEN"
check "GET /api/customers/2/health" 200 \
  "$BASE_URL/api/customers/2/health" \
  -H "Authorization: Bearer $TOKEN"
check "GET /api/customers/2/timeline" 200 \
  "$BASE_URL/api/customers/2/timeline" \
  -H "Authorization: Bearer $TOKEN"

# ---------------------------------------------------------------------------
# [9/9] customer_resources — depends on cloudcost (reads service_accounts),
# so it inherits the same "200 or acceptable-502" contract as bridge routes.
# Additionally, 404 is legit when the customer has no cloudcost match at all.
# ---------------------------------------------------------------------------
echo "[9/9] customer_resources tolerant probe (200 / 404 / acceptable 502)"
cr_code=$(curl -s -o /tmp/smoke.body -w '%{http_code}' \
  -H "Authorization: Bearer $TOKEN" \
  "$BASE_URL/api/customers/2/resources" || true)
if [[ "$cr_code" == "200" || "$cr_code" == "404" ]]; then
  green "  ok  GET /api/customers/2/resources  -> $cr_code (tolerated)"
  PASS=$((PASS+1))
elif [[ "$cr_code" == "502" ]]; then
  body=$(head -c 500 /tmp/smoke.body || true)
  if printf '%s' "$body" | python3 -c '
import json,sys
raw = sys.stdin.read()
try:
    obj = json.loads(raw)
except Exception:
    sys.exit(2)
detail = str(obj.get("detail", "")).lower()
sys.exit(0 if ("云管" in detail) or ("cloudcost" in detail) else 3)
' 2>/dev/null; then
    yellow "  ok  GET /api/customers/2/resources  -> 502 (acceptable: cloudcost upstream down)"
    PASS=$((PASS+1))
  else
    red   "  FAIL  GET /api/customers/2/resources  -> 502 without friendly envelope"
    red   "    body: $body"
    FAIL=$((FAIL+1))
  fi
else
  red   "  FAIL  GET /api/customers/2/resources  -> got $cr_code"
  red   "    body: $(head -c 200 /tmp/smoke.body)"
  FAIL=$((FAIL+1))
fi

echo
echo "Pass: $PASS   Fail: $FAIL"
[[ "$FAIL" -eq 0 ]]
