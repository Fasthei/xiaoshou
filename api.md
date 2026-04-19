# 云管 (cloudcost) → 销售系统 (xiaoshou) API 契约

> 本文档只描述**云管给销售系统暴露的 HTTP API**，以及销售系统怎么消费它们。
> 销售系统自己的内部 API 不列在这里。

---

## 0. 鉴权 & 基础约定

- 云管与销售系统共用同一个 **Casdoor**（organization=`operation`, app=`sales`）。
- `CloudCostClient` 在 `app/integrations/cloudcost.py` 里按以下优先级发鉴权头：
  1. 显式 `bearer_token`（转发调用方的 JWT，bridge/cc_sync 默认走这条）
  2. `CLOUDCOST_API_KEY` → `X-Api-Key`（运维可配的兜底）
  3. `CLOUDCOST_M2M_TOKEN` → `Authorization: Bearer …`（M2M 兜底）
  4. 都没配 → 匿名（仅适用本地测试 / legacy 部署）
- 路径基础：`${CLOUDCOST_ENDPOINT}` 形如 `https://cloudcost.…azurecontainerapps.io`
- 所有响应支持**两种形状**（调用方需兼容）：
  - 纯数组：`[{...}, {...}]`
  - 信封：`{"items":[...], "total":N}` / `{"data":[...]}`

---

## 1. 已接入（实际在销售系统里调用）

| 接口 | 作用 | 销售系统消费点 |
|---|---|---|
| `GET /api/health` | 心跳 | `CloudCostClient.health()` |
| `GET /api/auth/me` | 当前登录用户 | `CloudCostClient.auth_me()`（诊断用） |
| `GET /api/service-accounts/` | 货源列表（cloudcost 的 ServiceAccount） | 同步 → 本地 `resource` 表；账单/用量同步先拉这个再按 account_id 取明细 |
| `GET /api/service-accounts/{id}/costs` | 单账号近 N 天费用（legacy） | `cc_sync.sync_cloudcost_usage` 的 **fallback** 路径；新接口没落地的云管实例继续用 |
| `GET /api/suppliers/supply-sources/all` | 所有 supplier 源头 | 仅展示用（`resources/Top` 面板） |
| `GET /api/bills/` | **月度**账单（cloudcost 视角的聚合） | `cc_sync.sync_cloudcost_bills` → 本地 `cc_bill` 表 |
| `GET /api/alerts/rule-status` | 预警规则触发快照 | `cc_sync.sync_cloudcost_alerts` → 本地 `cc_alert` 表；briefing 直读 |
| `GET /api/dashboard/bundle` | 主管 Dashboard 一次性 bundle | `trend.py` / `bridge.py`（管理后台看板） |
| `GET /api/sync/last` | 云管端自身同步时间戳 | 调试用（`CloudCostClient.sync_last()`） |
| `GET /api/metering/summary` | 指定时间窗的总成本/总用量/记录数 | 趋势、汇总面板（替代本地 `by_status` 侧边凑数） |
| `GET /api/metering/daily` | 按日分桶成本/用量 | 客户抽屉里 **日度趋势** 图；主管 dashboard 的趋势线 |
| `GET /api/metering/by-service` | 按云服务名 (EC2/S3/BLOB/…) 分桶 | 客户详情 `by_service` panel |
| `GET /api/metering/detail` | 明细行（分页） | **cc_usage 同步的新真源**：`CloudCostClient.metering_detail_iter(...)` 按 account_id 流式拉全量，本地重聚合到 `cc_usage (customer_code × date)` |
| `GET /api/metering/detail/count` | 明细总行数 | 分页决策；防止死循环 |
| `GET /api/billing/detail` | 单笔账单明细（分页） | 账单导出 / 审计；未来 `bills_export` 按 line 导 CSV 时会切到这个 |
| `GET /api/billing/detail/count` | 账单明细总行数 | 分页决策 |

---

## 2. 计划接入（客户端已支持，消费端尚未切换）

- `billing/detail` 的深度集成：现在只加到 Client，尚未替换 `bills_export.py` 的导出管线。待账单中心 CSV 导出升级时再接入。
- `metering/summary` 替换主管 dashboard 的部分本地聚合：KPI 面板现在从本地 `cc_usage` 聚合，等 metering/summary 稳定后可直连，减一层本地缓存。
- `auth/me` 只在 Client 暴露，没有前端路由消费；用于 SSO 双系统诊断。

---

## 3. 明确不接入

### `POST /api/service-accounts/customer-assignments/sync`

**不用。** 理由：

- 销售系统的 **客户 → 货源** 归属真源是本地 `customer_resource` 表（销售在客户详情里手工勾选）。
- `customer-assignments/sync` 是云管侧的反向同步接口（把云管推断的归属写进 xiaoshou 或反过来）。一旦双写，两边会竞争同一份归属数据，人工勾选可能被自动推断覆盖。
- 本轮不做双向写同步，维持单向关系：
  - 云管负责 **原始计量** (metering/detail) + **账号元数据** (service-accounts)
  - 销售系统负责 **客户归属** (customer_resource) + **本地聚合** (cc_usage/cc_bill/bills_by_customer)

### `POST /api/*` 任何写接口（创建 service account / rule / bill / 调价）

销售系统**只读**云管。所有"客户的账单/客户的用量"是本地聚合出来的视图，不改云管底层数据。

---

## 4. 字段映射（重要不变量）

```
cloudcost.service_account.id                                  → resource(id?)          # 云管内部 id
cloudcost.service_account.external_project_id                 → resource.identifier_field   # 真正的跨系统 key
cloudcost.service_account.external_project_id                 = cc_bill.customer_code       # 账单 join key
cloudcost.service_account.external_project_id                 = cc_usage.customer_code      # 用量 join key
cloudcost.service_account.supplier_name                        → 次级 match_field（兜底）
```

销售系统**永远不把 `customer.customer_code` 当成 cloudcost 的 key**。客户归属只走 `customer_resource(customer_id, resource_id)` 这条桥。

### metering/detail → 本地 cc_usage 映射

`cc_sync.sync_cloudcost_usage` 对每个匹配到该 customer 的 service_account，调 `metering_detail_iter(account_id=a.id, start_date, end_date)` 流式拉明细，然后按 `date` 维度在本地聚合：

```python
cc_usage = {
  customer_code = customer.customer_code,
  date          = metering_row.date (YYYY-MM-DD),
  total_cost    = Σ metering_row.cost                (当日所有账号所有明细)
  total_usage   = Σ metering_row.usage/quantity
  record_count  = count of metering_row
  raw.accounts  = [
    {
      account_id = a.id,
      service    = metering_row.service / service_name,
      cost       = metering_row.cost,
      usage      = metering_row.usage,
      date       = metering_row.date,
      source     = "metering" | "legacy"          # 标记数据来源
    },
    ...
  ],
}
```

如果 `metering/detail` 调用失败，同步链路自动退回到旧的 `GET /api/service-accounts/{id}/costs`，`raw.accounts[*].source = "legacy"`，保证运维节奏与云管部署节奏解耦。

### bills_by_customer 聚合（不变）

`/api/bills/by-customer` 的口径**本轮不变**：
- 以 `customer_resource` 为真源，查出该客户的货源 `resource_id` 列表
- 每个 `resource.identifier_field` 去 `cc_bill` 里汇总
- 货源无 `identifier_field` / `cc_bill` 无命中 → fallback 到 `cc_usage.total_cost`

## 5. 错误处理约定

- 云管返回非 JSON → 抛 `httpx.DecodingError("cloudcost returned non-JSON: …")`，bridge 端捕获转 502。
- 云管 4xx/5xx → `httpx.HTTPStatusError`，调用点决定是 raise 还是降级到 mock/cache。
- `metering_detail_iter` 有 `max_pages` 安全阀（默认 500 页 × 500 行 = 250k 行），防止无限分页。

---

## 6. 变更记录

- 2026-04-19: 扩展 Client 支持 `/api/auth/me`、`/api/metering/*`、`/api/billing/detail*`；`cc_sync` 用量同步切到 `metering/detail`，保留 legacy fallback；明确不接入 `customer-assignments/sync`。
