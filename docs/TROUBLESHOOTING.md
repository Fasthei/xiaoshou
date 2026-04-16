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

**Fix** (PR #13)
Since xiaoshou and cloudcost share the same Casdoor tenant, the cheapest
correct thing is to **forward the caller's Casdoor JWT** rather than
provision a separate machine identity. `app/api/bridge.py`,
`app/api/trend.py`, and `app/api/customer_resources.py` now extract
`Authorization: Bearer <jwt>` from the inbound `Request` and pass it to
`CloudCostClient(..., bearer_token=...)`. The new `bearer_token` kwarg wins
over the old `CLOUDCOST_M2M_TOKEN` env fallback.

Operators do **not** need to set any new env var in prod. See
`docs/CLOUDCOST_AUTH.md` for the full story.

**Cheap reproducer**
```bash
# Same token against xiaoshou (before fix) and cloudcost directly:
# - cloudcost direct → 200
# - xiaoshou → 502 wrapping a 401
# After the fix: xiaoshou → 200 too.
curl -sS -H "Authorization: Bearer $TOKEN" "$API/api/bridge/alerts?month=$(date +%Y-%m)"
# → 200 [...]
```

**What to check first next time**
1. Caller token unexpired? Decode at jwt.io; `exp` must be future.
2. Caller has the role cloudcost's RBAC requires (e.g. `cloudcost.reader`).
   If cloudcost returns `403 missing required role`, the fix is a Casdoor
   role assignment, **not** a xiaoshou env tweak.
3. `CLOUDCOST_ENDPOINT` reachable from xiaoshou's egress (try `/api/health`).
4. If a background/system caller (no user context) needs cloudcost, wire
   `CLOUDCOST_M2M_TOKEN` as the fallback — see `docs/CLOUDCOST_AUTH.md §5`.

---

## 2026-04 · `DELETE /api/sales/users/:id/hard` → 500 IntegrityError (FK violation)

**Symptom**
- Admin clicks "硬删除" on a sales user → toast "删除失败 (500)".
- xiaoshou logs show
  `sqlalchemy.exc.IntegrityError: ... ForeignKeyViolation ...
   lead_assignment_log_from_user_id_fkey ...`
- Reproduces 100% on any sales user who has ever been a source or target of
  a `LeadAssignmentLog` entry.

**Root cause**
`hard_delete_user` in `app/api/sales.py` cleared `sales_rule` references and
recycled the user's customers, but left `lead_assignment_log.from_user_id`
and `lead_assignment_log.to_user_id` pointing at the row it was about to
`DELETE`. The FKs were declared without `ON DELETE SET NULL`, so Postgres
refused. The test suite missed this because SQLite's default is
`PRAGMA foreign_keys=OFF`.

**Fix** (PR #12)
- `app/api/sales.py::hard_delete_user`: before the `db.delete(su)` call,
  `UPDATE lead_assignment_log SET from_user_id/to_user_id = NULL` for the
  target user. Audit trail is preserved via the `reason` text column (it
  already embeds the deleted user's id + name).
- `app/models/sales.py`: add `ondelete="SET NULL"` to both FKs as a DB-layer
  safety net for future direct-SQL deletes.
- New regression test (`tests/test_sales_hard_delete_fk.py`) runs with
  `PRAGMA foreign_keys=ON` to mirror Postgres.
- Production DB migration (add `ON DELETE SET NULL` to existing FK
  constraints) is in the PR body — run after merge.

**Cheap reproducer**
```bash
# Pick any sales_user id that shows up in lead_assignment_log.from_user_id
# or .to_user_id — e.g. 1 or 2 in prod.
curl -sS -X DELETE -H "Authorization: Bearer $TOKEN" "$API/api/sales/users/1/hard"
# Before the fix: 500 + ForeignKeyViolation in logs.
# After:
# {"deleted_user_id":1,"deleted_name":"...","customers_recycled":N,
#  "rules_touched":M,"logs_nullified":K}
```

**What to check first next time**
1. Any new table with an FK to `sales_user.id` (or any user-like table)?
   Add `ondelete="SET NULL"` at the model level AND a matching cleanup step
   before `db.delete(...)` for the existing rows.
2. Is the prod migration applied? `\d+ lead_assignment_log` in psql should
   show `ON DELETE SET NULL` on both FK columns. If not, the handler's
   pre-UPDATE still protects you, but you lose the DB-layer safety net.
3. SQLite tests: make sure `PRAGMA foreign_keys=ON` is set on the test
   engine — see `tests/test_sales_hard_delete_fk.py` for the pattern.

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
