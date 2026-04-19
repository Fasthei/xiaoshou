# xiaoshou 销售系统文档索引

本目录是销售系统（xiaoshou）的**产品、架构、运维、接口**文档的唯一落脚点。
仓库根目录只保留 `README.md` / `CLAUDE.md` / `AGENTS.md` 三个约定文件，其它一切归档至此。

## 一、给 **运营大脑 / super-ops** 对接方

想直接通过 HTTP 调用销售系统的数据？**只看一份：**

- **[SUPER_OPS_API.md](./SUPER_OPS_API.md)** — xiaoshou → 运营大脑 的只读 API 契约
  - Base URL: `https://xiaoshou-api.braveglacier-e1a32a70.eastasia.azurecontainerapps.io/api/external`
  - 鉴权：`X-Api-Key: <SUPER_OPS_API_KEY>`（活性探针 `/meta/ping` 免鉴权）
  - 端点清单：客户、分配、货源、销售成员、分配规则、客户 AI 洞察
  - 每个端点都给了 Query 参数、响应示例、字段说明

> 运营大脑侧的 agent / workflow **不需要登录 Casdoor**，用运维下发的 `X-Api-Key` 即可调用 `/api/external/*`。

## 二、给 **云管 (cloudcost) 对接方 / 销售系统开发者**

销售系统如何消费云管 API：

- **[CLOUDCOST_API.md](./CLOUDCOST_API.md)** — 云管 → 销售系统 消费契约（§1 已接入 / §2 计划接入 / §3 明确不接入）
- **[CLOUDCOST_AUTH.md](./CLOUDCOST_AUTH.md)** — 共享 Casdoor 配置与 JWT 透传细节

## 三、产品 & 业务规则

- **[PRODUCT_PLAN.md](./PRODUCT_PLAN.md)** — 销售系统产品方案（定位 / 三角色分工 / 核心流程）
- **[TECH_DESIGN.md](./TECH_DESIGN.md)** — 技术实施方案（架构分层 / 模块划分）
- **[BUSINESS_FLOW_CHECKLIST.md](./BUSINESS_FLOW_CHECKLIST.md)** — 业务流程核对清单（验收用）
- **[ROLES.md](./ROLES.md)** — Casdoor 角色定义（`sales` / `sales-manager` / `ops` / `admin` / ...）

## 四、鉴权 & 部署

- **[AUTH.md](./AUTH.md)** — 后端 `require_auth` / `require_roles` 机制与 JWT 校验
- **[SSO.md](./SSO.md)** + [sso-templates/](./sso-templates/) — Casdoor 单点登录配置模板
- **[DEPLOY.md](./DEPLOY.md)** — Azure Container Apps / Static Web Apps 部署流程
- **[TROUBLESHOOTING.md](./TROUBLESHOOTING.md)** — 常见故障与排查

## 五、测试

- **[TEST.md](./TEST.md)** — 本地 / CI 测试流程

## 六、历史存档（不再维护）

- **[history/](./history/)** — 过往 session 工作日志（`findings.md` / `progress.md` / `task_plan.md`）

---

## 三张 API "入口图"

```
┌─────────────────────────────────────────────────────────────┐
│                     xiaoshou 销售系统 API                     │
├─────────────────┬─────────────────────┬─────────────────────┤
│   /api/*        │   /api/internal/*   │   /api/external/*   │
│  前端消费       │   云管 (cloudcost)  │   运营大脑 super-ops │
│  Casdoor JWT    │   M2M JWT / API Key │   X-Api-Key         │
│  所有 UI 功能   │   桥接 sync         │   只读快照 + AI 洞察 │
└─────────────────┴─────────────────────┴─────────────────────┘
       ↑                    ↑                     ↑
  AppLayout 菜单        bridge.py / cc_sync    SUPER_OPS_API.md
```

**三条 API 通道完全独立**：凭证独立轮换，路由独立挂载（见 `app/main.py`），权限独立判定。
