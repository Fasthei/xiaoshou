# Cloudcost Auth — how xiaoshou talks to 云管 when AUTH_ENFORCED=true

Up until Q1'26 the cloudcost (云管) API was read-only and anonymous. Starting
with the `AUTH_ENFORCED=true` rollout (see cloudcost repo), cloudcost now
rejects anonymous calls to every endpoint xiaoshou's bridge depends on
(`/api/alerts/rule-status`, `/api/bills/`, `/api/service-accounts/`,
`/api/suppliers/supply-sources/all`, `/api/dashboard/bundle`, `/api/sync/last`,
`/api/health`).

This document explains how xiaoshou authenticates outbound calls to cloudcost,
what env vars operators may set, and how to verify the wiring end-to-end.

---

## 1. Trust model — shared Casdoor, forwarded user JWT

xiaoshou and cloudcost share the **same Casdoor tenant**. Because of that, the
cheapest correct thing is for xiaoshou to **forward the caller's Casdoor
Bearer token** on outbound calls rather than use a separate machine identity.
This preserves per-user audit context downstream and needs zero operator
configuration.

| Direction                       | Caller       | Auth carrier (prod)                                           |
|---------------------------------|--------------|---------------------------------------------------------------|
| xiaoshou → cloudcost (outbound) | xiaoshou API | `Authorization: Bearer <caller's Casdoor JWT>` (forwarded as-is) |
| cloudcost → xiaoshou (inbound)  | cloudcost    | Casdoor M2M JWT **or** `X-Api-Key`, verified by `app/integrations/casdoor_m2m.py` |

The forwarding happens in the FastAPI handlers (`app/api/bridge.py`,
`app/api/trend.py`, `app/api/customer_resources.py`) — each extracts
`Authorization: Bearer <jwt>` from the inbound `Request` and passes it to
`CloudCostClient(..., bearer_token=...)`. See `_bearer_from_request` in
`app/api/bridge.py`.

Per-request side effects you can rely on:

- Cloudcost sees the same `sub` / `aud` / roles the end user has in xiaoshou.
- RBAC on cloudcost is enforced against the end user, not a service role. If
  cloudcost returns `403 missing required role`, the fix is a role assignment
  in Casdoor, **not** a xiaoshou env tweak.
- `/docs` and `/health` still work unauthenticated (they don't call cloudcost).

---

## 2. Precedence of credentials on `CloudCostClient`

`CloudCostClient` accepts three credential sources. They are tried in this
order and the first hit wins for the `Authorization` header:

1. **`bearer_token=...` kwarg** — forwarded caller JWT (prod path).
2. **`CLOUDCOST_M2M_TOKEN` env** — Casdoor client_credentials JWT
   (fallback; used by background jobs without a user context).
3. *(none)* → `Authorization` header is omitted → cloudcost returns `401`.

Independently, if `CLOUDCOST_API_KEY` is set it is **always** sent as
`X-Api-Key`. This is useful for local dev against a cloudcost deployment
that still accepts a static key.

| Var                       | Required | Notes                                                          |
|---------------------------|----------|----------------------------------------------------------------|
| `CLOUDCOST_ENDPOINT`      | yes      | Base URL, e.g. `https://cloudcost-api.<region>.azurecontainerapps.io` |
| `CLOUDCOST_MATCH_FIELD`   | no       | Which `service_account` attr equals `customer_code`. Default `external_project_id`. |
| `CLOUDCOST_M2M_TOKEN`     | no       | Casdoor client_credentials JWT fallback. Only consulted when no caller token is available. |
| `CLOUDCOST_API_KEY`       | no       | Static `X-Api-Key`. Useful for local dev.                      |

In production today **none of the cloudcost env vars need to be set** beyond
`CLOUDCOST_ENDPOINT` and `CLOUDCOST_MATCH_FIELD` — the caller's JWT does the
work.

---

## 3. Env vars on xiaoshou for the *inbound* direction (cloudcost → xiaoshou)

Cloudcost also pulls data from xiaoshou (`/api/internal/*`). Accept either a
Casdoor M2M JWT whose `aud` is in the allowlist, or a static API key:

| Var                               | Purpose                                                       |
|-----------------------------------|---------------------------------------------------------------|
| `CASDOOR_INTERNAL_ALLOWED_CLIENTS`| Comma-sep list of Casdoor client IDs allowed to hit `/api/internal/*`. |
| `XIAOSHOU_INTERNAL_API_KEY`       | Static shared secret. Sent by cloudcost as `X-Api-Key`.       |

See `app/integrations/casdoor_m2m.py::verify_internal` for the verification
path.

---

## 4. How a request actually flows

```
Browser (user Casdoor JWT)
  │  Authorization: Bearer eyJ...  (the user's token)
  ▼
xiaoshou /api/bridge/alerts?month=2026-04
  │  require_auth → validates aud/iss on the user token
  │  _bearer_from_request → extracts raw "eyJ..." string
  │  CloudCostClient(bearer_token="eyJ...")
  ▼
cloudcost /api/alerts/rule-status
  │  validates the SAME token (same Casdoor, same aud accepted)
  │  RBAC check against the user's roles
  ▼
  200 (happy) | 401 (expired token) | 403 (missing role) | 500 (cloudcost bug)
```

If the caller token is expired or missing, the bridge handler catches the
resulting `401` as an `httpx.HTTPStatusError` and wraps it in the
`502 {"detail": "云管暂不可达: HTTPStatusError: ..."}` envelope the SPA knows how
to render.

---

## 5. M2M fallback (CLOUDCOST_M2M_TOKEN)

There is no user context for scheduled/system callers (cron jobs, background
sync, etc.). For those, obtain a Casdoor client_credentials token at startup
and set it via env:

```bash
curl -sS -X POST \
  "$CASDOOR_ENDPOINT/api/login/oauth/access_token" \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode "grant_type=client_credentials" \
  --data-urlencode "client_id=$CASDOOR_CLIENT_ID" \
  --data-urlencode "client_secret=$CASDOOR_CLIENT_SECRET" \
  | jq -r .access_token
```

Refresh every 30 minutes and write back into the Container App's secret
store. Never bake tokens into images.

In production today no scheduled-job path exercises cloudcost, so
`CLOUDCOST_M2M_TOKEN` is typically unset.

---

## 6. Verifying the wiring end-to-end

Against a live environment:

```bash
export TOKEN=<fresh Casdoor token from Casdoor /access_token>
export API=https://xiaoshou-api.<region>.azurecontainerapps.io

# 200 means forwarding works end-to-end.
# 502 with detail "云管暂不可达" means the outbound call failed — usually
#   a stale/expired user token, or the user lacks the cloudcost role.
curl -sS -H "Authorization: Bearer $TOKEN" "$API/api/bridge/alerts?month=$(date +%Y-%m)"
curl -sS -H "Authorization: Bearer $TOKEN" "$API/api/bridge/bills?month=$(date +%Y-%m)&page_size=5"
curl -sS -H "Authorization: Bearer $TOKEN" "$API/api/trend/daily?days=7"
curl -sS -H "Authorization: Bearer $TOKEN" "$API/api/customers/2/resources"
```

Or just run the smoke script:

```bash
BASE_URL=$API TOKEN=$TOKEN bash scripts/smoke-test.sh
```

All four bridge-family routes must return either `200` or the acceptable-502
envelope. Anything else (blank 502 from ingress, 401 bubbling up, or 5xx with
a Python stack trace) is a real regression — page the platform team.

If you see `502 "... cloudcost returned 403 ... missing required role ..."`,
that's a **cloudcost-side RBAC problem**: assign the right role to the user
in Casdoor. It is not a xiaoshou bug.

---

## 7. Rollback / break-glass

If cloudcost revokes `AUTH_ENFORCED` (e.g. during an incident), xiaoshou
continues to work: forwarded headers are ignored by anonymous cloudcost,
and responses come back normally. You do **not** need to redeploy xiaoshou
to respond to a cloudcost auth change.

If xiaoshou must stop calling cloudcost entirely (blast-radius isolation):

```bash
# unsets the client; bridge returns 400 "CLOUDCOST_ENDPOINT not configured"
CLOUDCOST_ENDPOINT=
```

Frontend is expected to render the 400/502 states gracefully (see
`frontend/src/pages/{Alerts,Bills,Dashboard,Resources}.tsx`).
