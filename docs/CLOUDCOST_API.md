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
| `GET /api/metering/detail` | 明细行（分页） | **cc_usage 同步的新真源**：`CloudCostClient.metering_detail_iter(...)` 按 account_id 流式拉全量，本地重聚合到 `cc_usage (customer_code × date)`；每行 metering 的 `service` 同时存入 `cc_usage.raw.accounts[]`，供 `/api/usage/breakdown` 二次聚合到「客户 → 货源 → 服务类目」三层下钻 |
| `GET /api/metering/detail/count` | 明细总行数 | 分页决策；防止死循环 |
| `GET /api/billing/detail` | 单笔账单明细（分页） | 账单导出 / 审计；未来 `bills_export` 按 line 导 CSV 时会切到这个 |
| `GET /api/billing/detail/count` | 账单明细总行数 | 分页决策 |

### 销售系统暴露出去给前端的对齐接口（非云管接口，仅供对照）

| 接口 | 作用 | 数据来源 |
|---|---|---|
| `POST /api/sync/cloudcost/run` | 账单中心「同步云管」按钮；距上次成功 SyncLog 起算 days，串行跑 bills(当月) + alerts(当月) + usage(days)；首次 365 天 | 调上面 cloudcost 的 `metering/detail` / `/api/bills/` / `/api/alerts/rule-status` |
| `GET /api/sync/cloudcost/last-sync` | 前端展示"距上次同步 X 天" | 本地 `sync_log` 表 |
| `GET /api/bills/by-customer` | 账单中心列表（客户 × 货源）| 本地 `cc_usage.total_cost`（原价）+ `allocation.discount_rate`（订单折扣）+ `bill_adjustment`（覆盖）|
| `GET /api/usage/breakdown` | 预警中心「用量查看」（客户 → 货源 → 服务）| 本地 `cc_usage.raw.accounts[]` 按 `service` 分桶 + 类目 mapping |

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
  - 销售系统负责 **客户归属** (customer_resource) + **本地聚合** (cc_usage / cc_bill / bills_by_customer / usage_breakdown)

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
      account_id          = a.id,
      external_project_id = a.external_project_id,
      provider            = metering_row.provider          # "azure" / "aws" / ...
      product             = metering_row.product           # "Azure App Service" / "Claude Sonnet 4 (Bedrock)"
      sku                 = metering_row.usage_type        # **SKU 粒度**，如 "P0v3 App" / "USE1-MP:USE1_OutputTokenCount-Units"
      region              = metering_row.region            # "eastus2" / "use1"
      usage_unit          = metering_row.usage_unit        # "1 Hour" / "1 GB" / "Units"
      service             = product                         # 兼容老字段，=== product
      cost                = metering_row.cost,
      usage               = metering_row.usage_quantity,
      date                = metering_row.date,
      source              = "metering" | "legacy"         # 标记数据来源
    },
    ...
  ],
}
```

如果 `metering/detail` 调用失败，同步链路自动退回到旧的 `GET /api/service-accounts/{id}/costs`，`raw.accounts[*].source = "legacy"`，保证运维节奏与云管部署节奏解耦。

### 客户 → 货源 解析（bills_by_customer / usage_breakdown 共用）

账单中心（`/api/bills/by-customer`）和用量查看（`/api/usage/breakdown`）共用一个 helper：`app/services/customer_resource_resolver.resolve_customer_resources()`。两层策略：

1. **手工关联**（`customer_resource` 表）：始终生效。销售在客户详情里勾选的真源。
2. **自然匹配兜底**：`resource.identifier_field == customer.customer_code`。**只对销售主管 / admin / ops 启用**。

> 为什么加第 2 层？业务要求"销售主管不会去关联客户，但必须看到所有客户用量"（CLAUDE.md §2）。销售主管不承担手工勾选工作，让他在账单中心/用量查看里仍能看到完整视图。销售角色不启用自然匹配，避免越权。

### bills_by_customer 聚合口径

`/api/bills/by-customer` 对每个 (客户, 货源) 出一行：

```
原价     = Σ cc_usage.total_cost   (按 resource.identifier_field × 当月)
折扣率   = 最近一条 approved allocation.discount_rate   (订单上定的)
覆盖     = bill_adjustment.discount_rate_override ± surcharge   (账单中心手工调整)
折后价   = 原价 × (1 − 有效折扣率/100) + surcharge
```

> **不再读 cc_bill 的 original_cost / final_cost** — 避免把云管成本视角暴露给销售。

### usage_breakdown 聚合（/api/usage/breakdown）

粒度已从"服务"下放到 **SKU**（cloudcost `usage_type`）。每层聚合：

```
客户 (customer)
 └─ 货源 (resource — resolve_customer_resources 给出的集合)
     └─ SKU (按 (provider, product, sku, region, usage_unit) 去重分桶)
         + 类目 category = compute / ai / database / storage / network / other
           （按 product name 关键词推断，详见 app/api/usage_breakdown.py _CATEGORIES）
```

输出：
- `total_cost / total_usage / customer_count` 顶部统计
- `categories / category_labels` 前端画类目 Tag 用
- `customers[*].resources[*].skus[*]` 嵌套数组；每个 `sku` 条目包含
  `provider / product / sku / region / usage_unit / category / category_label /
  cost / usage / record_count`
- `customers[*].total_cost / resources[*].total_cost` 逐层累计

前端（预警中心「用量查看」Tab）把 `customers[*].resources[*].skus[*]` 扁平化
后按 cost 降序，用 **recharts 水平条形图** 画 TopN（默认 30）。一条柱子 = 一个
"客户 · 货源 · 产品 / SKU"。颜色按 category 着色。支持筛选客户 / 货源 / 类目。

兼容老数据：同步器旧版本只往 `raw.accounts[*]` 写 `service` 字段；聚合端 read
时优先 `product`/`sku`，回退 `service`（此时 product==sku，SKU 粒度退化成服务
粒度，前端仍可画图）。新数据同步后自动升级。

类目判定的关键词模式**顺序敏感**：compute → ai → database → storage → network → other（一条云服务名按顺序匹配第一条）。加新关键词直接改 `_CATEGORIES` 常量。

## 5. 错误处理约定

- 云管返回非 JSON → 抛 `httpx.DecodingError("cloudcost returned non-JSON: …")`，bridge 端捕获转 502。
- 云管 4xx/5xx → `httpx.HTTPStatusError`，调用点决定是 raise 还是降级到 mock/cache。
- `metering_detail_iter` 有 `max_pages` 安全阀（默认 500 页 × 500 行 = 250k 行），防止无限分页。

---

## 6. 变更记录

- 2026-04-19: 扩展 Client 支持 `/api/auth/me`、`/api/metering/*`、`/api/billing/detail*`；`cc_sync` 用量同步切到 `metering/detail`，保留 legacy fallback；明确不接入 `customer-assignments/sync`。
- 2026-04-22: 同步层从路由里剥出 `app/services/cloudcost_sync.py`；新增 `POST /api/sync/cloudcost/run`（账单中心「同步云管」按钮，按 `sync_log` 上次成功时间算 days 增量）+ `GET /api/sync/cloudcost/last-sync`。权限 `sales / sales-manager / admin / ops`。
- 2026-04-23:
  - 新增 `GET /api/usage/breakdown`（预警中心「用量查看」Tab，客户 → 货源 → 服务三层下钻，按服务名关键词推断类目 compute/ai/database/storage/network/other）。
  - 抽出 `customer_resource_resolver` 共享 helper：`bills_by_customer` 和 `usage_breakdown` 都走它；销售主管 / admin / ops 启用 `identifier_field == customer_code` 自然匹配兜底（业务需求：销售主管不去关联客户也要看到全部客户用量）；销售视角不自动补。
  - 账单中心聚合口径改为「原价(cc_usage) × 订单折扣(allocation) + 覆盖/手续费(bill_adjustment)」，不再读 cc_bill.original_cost / final_cost。
- 2026-04-23b: 用量查看下沉到 **SKU 粒度**。
  - 同步器 (`cloudcost_sync.do_sync_usage_for_customer`) 把 metering/detail 的
    `product / usage_type / region / usage_unit / provider` 一并存进
    `cc_usage.raw.accounts[]`；旧的 `service` 字段保留作为 `product` 别名.
  - `/api/usage/breakdown` 聚合 key 从 `service` 改为
    `(provider, product, sku, region, usage_unit)`；响应里 `resources[*].services`
    字段更名为 `resources[*].skus`，每个 SKU 带完整规格信息.
  - 预警中心「用量查看」Tab 前端改为 recharts 水平条形图 (一柱 = 一个客户×货源×SKU)，
    支持客户 / 货源 / 类目筛选 + TopN 滑杆；删除原嵌套表格.
