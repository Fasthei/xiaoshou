# 超级运营中心对接文档 (xiaoshou → super-ops)

> 本文档描述 **销售系统 (xiaoshou) 对超级运营中心暴露的只读 API**。所有接口在 `/api/external/*`，独立于面向前端的 `/api/*` 与面向云管的 `/api/internal/*`，凭证可独立轮换。

## 基本信息

| 项 | 值 |
|---|---|
| **Base URL (生产)** | `https://xiaoshou-api.braveglacier-e1a32a70.eastasia.azurecontainerapps.io/api/external` |
| **Base URL (本地)** | `http://localhost:8000/api/external` |
| **鉴权方式** | 请求头 `X-Api-Key: <SUPER_OPS_API_KEY>` |
| **编码** | 请求/响应 UTF-8, Content-Type `application/json` |
| **速率限制** | 暂无，建议自行节流 < 100 req/s |
| **时区** | 所有 ISO 8601 时间戳均为 **服务器本地时区 (Asia/Shanghai, +08:00)**，无 tz 后缀时按此解释 |
| **版本策略** | 无版本前缀，向后兼容新增字段；如破坏性变更会单独沟通 |

### 如何拿到 `SUPER_OPS_API_KEY`

在 Azure Container App `xiaoshou-api` 的 secret 里以 `super-ops-api-key` 命名存储，环境变量 `SUPER_OPS_API_KEY` 引用。由销售系统管理员分发给超运中心负责人。

本地开发在 `.env` 里设 `SUPER_OPS_API_KEY=<随便一串>` 即可。

### 活性检查

```bash
curl https://xiaoshou-api.braveglacier-e1a32a70.eastasia.azurecontainerapps.io/api/external/meta/ping
# => {"ok":true,"service":"xiaoshou-external","ts":"2026-04-15T23:55:00.000000"}
```

注意：`meta/ping` **不校验 X-Api-Key**（只用于可达性嗅探）。**所有业务端点都必须带 `X-Api-Key`**。

### 鉴权失败

```
HTTP/1.1 401 Unauthorized
{"detail": "invalid X-Api-Key"}
```

---

## 端点清单

| Method | Path | 说明 |
|---|---|---|
| GET | `/meta/ping` | 活性检查 (免鉴权) |
| GET | `/customers` | 客户列表 (分页 + 过滤) |
| GET | `/customers/{id}` | 客户详情 |
| GET | `/customers/{id}/assignment-log` | 客户分配历史 |
| GET | `/customers/{id}/insight/runs` | AI 洞察运行列表 |
| GET | `/customers/{id}/insight/facts` | AI 洞察事实库 |
| GET | `/allocations` | 分配记录列表 |
| GET | `/allocations/{id}/history` | 分配变更流水 |
| GET | `/resources` | 货源列表 |
| GET | `/sales/users` | 销售成员 |
| GET | `/sales/rules` | 分配规则 |

---

## 详细接口

### GET `/customers`

客户列表。

**Query 参数**
| 名 | 类型 | 默认 | 说明 |
|---|---|---|---|
| page | int | 1 | 页码 |
| page_size | int | 50 | 每页, 最大 500 |
| industry | string | - | 精确匹配 |
| region | string | - | 精确匹配 |
| customer_status | string | - | active / inactive / frozen / prospect |
| sales_user_id | int | - | 所属销售 id |
| only_unassigned | bool | false | true → 只返回未分配给任何销售的客户 |
| updated_since | ISO8601 | - | 仅返回 updated_at ≥ since (用于增量同步) |

**响应示例**

```json
{
  "total": 18,
  "page": 1,
  "page_size": 50,
  "items": [
    {
      "id": 2,
      "customer_code": "CUST-68A38417",
      "customer_name": "会伴",
      "industry": "科研服务",
      "region": null,
      "customer_level": null,
      "customer_status": "active",
      "sales_user_id": 2,
      "operation_user_id": null,
      "current_resource_count": 0,
      "current_month_consumption": 0.0,
      "source_system": "gongdan",
      "source_id": "u-xxxx",
      "last_follow_time": null,
      "created_at": "2026-04-15T10:15:04.001354",
      "updated_at": "2026-04-15T15:49:08.431617"
    }
  ]
}
```

### GET `/customers/{id}`

单客户详情，字段同上单条。404 时返回 `{"detail":"客户不存在"}`。

### GET `/customers/{id}/assignment-log`

该客户的商机分配/再分配/回收历史。按 id 升序。

```json
{
  "customer_id": 2,
  "items": [
    {
      "id": 1,
      "from_user_id": null,
      "to_user_id": 2,
      "trigger": "auto",
      "rule_id": 2,
      "reason": "auto-assign via rule '兜底'",
      "at": "2026-04-15T15:49:08.431617"
    }
  ]
}
```

`trigger` 枚举：`manual` / `auto` / `recycle` / `import`。
`to_user_id=null` 且 `trigger=recycle` 代表该次回收退回商机池。

### GET `/customers/{id}/insight/runs`

该客户的 AI 洞察 agent 运行列表 (降序)。

```json
{
  "customer_id": 2,
  "items": [
    {
      "id": 3,
      "status": "completed",
      "steps_total": 12,
      "steps_done": 4,
      "started_at": "2026-04-15T15:27:48.728656",
      "completed_at": "2026-04-15T15:28:43.998691",
      "summary": "# 会伴 洞察速览\n..."
    }
  ]
}
```

### GET `/customers/{id}/insight/facts`

该客户 agent 抓出来的所有事实。可选 `?category=` 过滤 (`basic` / `people` / `tech` / `news` / `event` / `other`)。

```json
{
  "customer_id": 2,
  "items": [
    {
      "id": 1,
      "category": "basic",
      "content": "会伴定位为信息技术最新国际会议和期刊列表平台...",
      "source_url": "https://www.myhuiban.com/",
      "fingerprint": "94396740b5d60f8c7cfd505fa04a95c4ea139a33",
      "run_id": 2,
      "discovered_at": "2026-04-15T15:18:12.123456"
    }
  ]
}
```

fingerprint = `sha1(category::normalized_content)`，同客户同指纹不会重复。

### GET `/allocations`

分配记录。

**Query 参数**
| 名 | 类型 | 默认 | 说明 |
|---|---|---|---|
| page | int | 1 | |
| page_size | int | 50 | 最大 500 |
| include_cancelled | bool | false | true 时包含 allocation_status=CANCELLED 的记录 |
| customer_id | int | - | 按客户过滤 |
| updated_since | ISO8601 | - | 增量同步 |

```json
{
  "total": 35,
  "page": 1,
  "page_size": 50,
  "items": [
    {
      "id": 1,
      "allocation_code": "ALLOC-20260415120000",
      "customer_id": 2,
      "resource_id": 7,
      "allocated_quantity": 10,
      "unit_cost": 120.50,
      "unit_price": 180.00,
      "total_cost": 1205.00,
      "total_price": 1800.00,
      "profit_amount": 595.00,
      "allocation_status": "PENDING",
      "created_at": "...",
      "updated_at": "..."
    }
  ]
}
```

### GET `/allocations/{id}/history`

该分配的字段级变更流水。从创建后发生过的每次 `quantity/unit_price/status/...` 改动一行。

```json
{
  "allocation_id": 1,
  "items": [
    {"id": 3, "field": "cancel", "old_value": "PENDING", "new_value": "CANCELLED", "reason": "客户退单", "at": "..."},
    {"id": 2, "field": "allocated_quantity", "old_value": "10", "new_value": "5", "reason": null, "at": "..."},
    {"id": 1, "field": "unit_price", "old_value": "200.00", "new_value": "180.00", "reason": null, "at": "..."}
  ]
}
```

### GET `/resources`

货源列表。分页同上。

### GET `/sales/users`

销售成员。`active_only` 默认 true，传 `false` 返回全部含停用。

### GET `/sales/rules`

分配规则，按 priority 升序。`sales_user_ids` 非空表示轮询模式，`cursor` 表示下次派给列表的 `cursor % len` 位。

```json
{
  "items": [
    {
      "id": 1, "name": "华东能源",
      "industry": "能源", "region": "华东", "customer_level": null,
      "sales_user_id": 3, "sales_user_ids": null, "cursor": 0,
      "priority": 10, "is_active": true
    },
    {
      "id": 2, "name": "AI 轮询",
      "industry": "AI", "region": null, "customer_level": null,
      "sales_user_id": null, "sales_user_ids": [5, 6, 7], "cursor": 42,
      "priority": 20, "is_active": true
    }
  ]
}
```

---

## 推荐消费模式

### 1. 增量同步客户到超运侧
```
每 10 分钟:
  last = localStorage.get("xiaoshou.customers.last_sync") or "1970-01-01"
  page = 1
  while True:
    resp = GET /customers?updated_since={last}&page={page}&page_size=500
    upsert resp.items to super-ops.customers
    if page * 500 >= resp.total: break
    page += 1
  localStorage.set("xiaoshou.customers.last_sync", now_iso())
```

### 2. 实时拉单客户 AI 洞察展示
```
当超运看客户 X:
  runs = GET /customers/X/insight/runs
  facts = GET /customers/X/insight/facts
  render(runs[0].summary, facts grouped by category)
```

### 3. 对账分配审计
```
每日 00:30:
  allocs = GET /allocations?updated_since=yesterday&include_cancelled=true
  for a in allocs.items:
    hist = GET /allocations/{a.id}/history
    archive to super-ops.audit_trail
```

---

## 错误码

| HTTP | 含义 |
|---|---|
| 200 | OK |
| 400 | 参数错误 (格式不对, updated_since 不是合法 ISO8601, 等) |
| 401 | X-Api-Key 缺失或错误 |
| 404 | 资源 (客户/分配/货源) 不存在或已软删 |
| 5xx | 服务端错误，业务端请带 exponential backoff 重试 |

---

## 变更日志

- **2026-04-15** 首版：`/customers`, `/allocations`, `/resources`, `/sales/users`, `/sales/rules`, `/customers/{id}/assignment-log`, `/customers/{id}/insight/{runs,facts}`, `/allocations/{id}/history`, `/meta/ping`。
