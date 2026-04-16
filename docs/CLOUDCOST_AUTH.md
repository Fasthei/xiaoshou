# Cloudcost Auth — how xiaoshou talks to 云管 when AUTH_ENFORCED=true

Up until Q1'26 the cloudcost (云管) API was read-only and anonymous. Starting
with the `AUTH_ENFORCED=true` rollout (see cloudcost repo), cloudcost now
rejects anonymous calls to every endpoint xiaoshou's bridge depends on
(`/api/alerts/rule-status`, `/api/bills/`, `/api/service-accounts/`,
`/api/suppliers/supply-sources/all`, `/api/dashboard/bundle`, `/api/sync/last`,
`/api/health`).

This document explains how xiaoshou authenticates outbound calls to cloudcost,
what env vars operators must set, and how to verify the wiring end-to-end.

---

## 1. Trust model

xiaoshou is a server-side Python (FastAPI) app. It talks to cloudcost in **two
directions**:

| Direction                       | Caller       | Auth carrier                                  |
|---------------------------------|--------------|-----------------------------------------------|
| xiaoshou → cloudcost (outbound) | xiaoshou API | `Authorization: Bearer <M2M-JWT>` **or** `X-Api-Key: <static-key>` |
| cloudcost → xiaoshou (inbound)  | cloudcost    | Same pair, verified by `app/integrations/casdoor_m2m.py` |

End-user Casdoor tokens (issued to the SPA) are **never** forwarded to
cloudcost. Cloudcost doesn't know xiaoshou's users — it trusts the xiaoshou
service identity instead. The user's Casdoor token only passes `require_auth`
on xiaoshou's own edge (e.g. `/api/bridge/*`); after that point xiaoshou
swaps in its own service credentials when calling cloudcost.

---

## 2. Env vars on xiaoshou (outbound)

Set exactly one of the two — both will work together if both are set, but only
one is required.

```bash
# Option A: preferred — Casdoor-issued M2M JWT (machine-to-machine, short-lived)
CLOUDCOST_M2M_TOKEN=eyJ...           # refreshed by sidecar / cronjob
# Option B: static fallback for bootstrap (before cloudcost joins Casdoor)
CLOUDCOST_API_KEY=<32+ random bytes>
```

`CloudCostClient` (see `app/integrations/cloudcost.py`) will read these from
env at construction time and forward them on every outbound request:

```
X-Api-Key: <CLOUDCOST_API_KEY>                 # if set
Authorization: Bearer <CLOUDCOST_M2M_TOKEN>    # if set
```

Other cloudcost-related env:

| Var                       | Required | Notes                                              |
|---------------------------|----------|----------------------------------------------------|
| `CLOUDCOST_ENDPOINT`      | yes      | Base URL, e.g. `https://cloudcost-api.<region>.azurecontainerapps.io` |
| `CLOUDCOST_MATCH_FIELD`   | no       | Which `service_account` attr equals `customer_code`. Default `external_project_id`. |
| `CLOUDCOST_M2M_TOKEN`     | one of   | Casdoor client_credentials JWT. Rotate hourly.      |
| `CLOUDCOST_API_KEY`       | one of   | Shared-secret static key. Rotate on incident.       |

Unset both → outbound becomes anonymous and cloudcost returns `401/403`,
which the bridge layer converts to the friendly `502 {"detail": "云管暂不可达..."}`
envelope. That is the observable signal that auth isn't wired up yet.

---

## 3. Env vars on xiaoshou (inbound, for cloudcost → xiaoshou)

Cloudcost also pulls data from xiaoshou (`/api/internal/*`). Accept either a
Casdoor M2M JWT whose `aud` is in the allowlist, or the same static API key:

| Var                               | Purpose                                         |
|-----------------------------------|-------------------------------------------------|
| `CASDOOR_INTERNAL_ALLOWED_CLIENTS`| Comma-sep list of Casdoor client IDs allowed to hit `/api/internal/*`. |
| `XIAOSHOU_INTERNAL_API_KEY`       | Static shared secret. Sent by cloudcost as `X-Api-Key`. |

See `app/integrations/casdoor_m2m.py::verify_internal` for the verification
path.

---

## 4. Token acquisition (Casdoor client_credentials)

```bash
curl -sS -X POST \
  "$CASDOOR_ENDPOINT/api/login/oauth/access_token" \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode "grant_type=client_credentials" \
  --data-urlencode "client_id=$CASDOOR_CLIENT_ID" \
  --data-urlencode "client_secret=$CASDOOR_CLIENT_SECRET" \
  | jq -r .access_token
```

For production, use a sidecar / cronjob that refreshes `CLOUDCOST_M2M_TOKEN`
every 30 minutes (tokens are typically ~1 h) and writes to the Container App's
secret store. Never bake tokens into images.

---

## 5. Verifying the wiring end-to-end

Against a live environment:

```bash
export TOKEN=<user-casdoor-token>
export API=https://xiaoshou-api.<region>.azurecontainerapps.io

# 200 means xiaoshou → cloudcost succeeded (auth passed both hops).
# 502 with detail "云管暂不可达" means xiaoshou edge is fine but the outbound
# call to cloudcost failed — usually a missing/stale M2M token.
curl -sS -H "Authorization: Bearer $TOKEN" "$API/api/bridge/alerts?month=$(date +%Y-%m)"
curl -sS -H "Authorization: Bearer $TOKEN" "$API/api/bridge/bills?month=$(date +%Y-%m)&page_size=5"
curl -sS -H "Authorization: Bearer $TOKEN" "$API/api/trend/daily?days=7"
```

Or just run the smoke script (token + API exported):

```bash
BASE_URL=$API TOKEN=$TOKEN bash scripts/smoke-test.sh
```

All three bridge routes must return either `200` or the acceptable-502
envelope. Anything else (especially blank 502 from ingress, 401, or 5xx with a
Python stack trace) is a real regression — page the platform team.

---

## 6. Rollback / break-glass

If cloudcost revokes `AUTH_ENFORCED` (e.g. during an incident), xiaoshou
continues to work: the outbound headers are ignored by anonymous cloudcost,
and responses come back normally. You do **not** need to redeploy xiaoshou to
respond to a cloudcost auth change.

If xiaoshou must stop calling cloudcost entirely (blast-radius isolation):

```bash
# unsets the client; bridge returns 400 "CLOUDCOST_ENDPOINT not configured"
CLOUDCOST_ENDPOINT=
```

Frontend is expected to render the 400/502 states gracefully (see
`frontend/src/pages/{Alerts,Bills,Dashboard,Resources}.tsx`).
