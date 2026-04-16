# Troubleshooting — recent bugs and their fixes

This is a short, post-mortem-style log kept for the next on-call. For each
incident we record: what users saw, root cause, the fix, and a cheap
reproducer so you can verify it really is the same bug before applying an
old fix.

Issues are listed newest-first.

---

## 2026-04 · Bridge 502 on every `/api/bridge/*` and `/api/trend/*` call (cloudcost `AUTH_ENFORCED=true`)

**Symptom**
- SPA Dashboard, Alerts, Bills, Resources pages all show the friendly banner
  "云管暂不可达". No stack trace in xiaoshou logs — just `httpx.HTTPStatusError:
  401 Unauthorized` from the outbound cloudcost client.
- `curl -H "Authorization: Bearer $USER_TOKEN" $API/api/bridge/alerts` returns
  `502 {"detail": "云管暂不可达: HTTPStatusError: Client error '401 Unauthorized'..."}`

**Root cause**
Cloudcost enabled `AUTH_ENFORCED=true`. Historically xiaoshou's
`CloudCostClient` called cloudcost anonymously (the code pre-dated
`X-Api-Key` support on cloudcost). The end-user's Casdoor token lives on the
SPA→xiaoshou hop only and is not forwarded — cloudcost doesn't know xiaoshou
users.

**Fix**
`app/integrations/cloudcost.py` now forwards service credentials on every
outbound request:

- `Authorization: Bearer $CLOUDCOST_M2M_TOKEN` (Casdoor client_credentials JWT), **and/or**
- `X-Api-Key: $CLOUDCOST_API_KEY` (static fallback).

Operators must set at least one on the xiaoshou Container App. See
`docs/CLOUDCOST_AUTH.md` for the full story.

**Cheap reproducer**
```bash
# Before the fix (or with both envs unset):
CLOUDCOST_M2M_TOKEN= CLOUDCOST_API_KEY= \
  curl -sS -H "Authorization: Bearer $TOKEN" "$API/api/bridge/alerts?month=$(date +%Y-%m)"
# → 502 {"detail":"云管暂不可达: HTTPStatusError: ... 401 ..."}

# After (with a good M2M token set):
curl -sS -H "Authorization: Bearer $TOKEN" "$API/api/bridge/alerts?month=$(date +%Y-%m)"
# → 200 [...]
```

**What to check first next time**
1. `CLOUDCOST_M2M_TOKEN` present and unexpired? Decode at jwt.io; `exp` must be future.
2. Its `aud` is in cloudcost's allowlist (cloudcost-side env).
3. Static `CLOUDCOST_API_KEY` hasn't been rotated without updating xiaoshou.
4. `CLOUDCOST_ENDPOINT` is reachable from xiaoshou's egress (try `/api/health`).

---

## 2026-04 · `DELETE /api/sales/users/:id` → 500 IntegrityError (FK violation)

**Symptom**
- Admin clicks "停用" on a sales user → toast "删除失败 (500)".
- xiaoshou logs show
  `sqlalchemy.exc.IntegrityError: ... foreign key constraint ... sales_attribution.user_id`.

**Root cause**
Sales users are referenced by `sales_attribution.user_id` with a hard FK and
no `ON DELETE` rule. The DELETE endpoint tried a row-level hard delete and
tripped the FK.

**Fix**
Switched to a **soft delete**: `active=False`. The endpoint (and related
`active_only` filters) now exclude inactive users from default listings, and
historical `sales_attribution` rows keep pointing at the user (audit-safe).

**Cheap reproducer**
```bash
# Create a test sales user, attribute a customer to them, try hard delete.
# Before the fix: 500.
# After: 200, and GET /api/sales/users?active_only=false still lists them.
curl -sS -H "Authorization: Bearer $TOKEN" "$API/api/sales/users?active_only=false" | jq '.[] | {id,name,active}'
```

**What to check first next time**
1. Any new table referencing `sales_user.id`? Add it to the `active_only`
   filter set, not another hard-delete path.
2. Frontend should send `active=false` PATCH rather than DELETE for any
   entity that participates in historical joins. Mirror the pattern used
   here for new entities.

---

## Reading guide

- `docs/CLOUDCOST_AUTH.md` — full env/var reference for the cloudcost wiring.
- `scripts/smoke-test.sh` — run after every deploy; also usable as a
  diagnostic during incidents. Token-gated routes are skipped unless `TOKEN=`
  is set.
- `docs/DEPLOY.md` — deployment targets and revision naming.

## When in doubt, run the smoke

```bash
export TOKEN=<casdoor-user-or-m2m-token>
export BASE_URL=https://xiaoshou-api.<region>.azurecontainerapps.io
bash scripts/smoke-test.sh
```

Everything green → xiaoshou is fine and the problem is downstream (cloudcost,
gongdan, Casdoor). Something red → start from the first `FAIL` line and
follow the relevant section above.
