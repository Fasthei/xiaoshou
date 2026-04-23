# xiaoshou 销售系统

`xiaoshou` 是一个面向销售团队的全栈系统：后端使用 FastAPI，前端使用 React + Vite + Ant Design，认证统一接入 Casdoor，并部署在 Azure（Container Apps + Static Web Apps）。

## 系统定位

- 销售为主，运营为辅
- 角色分工：`sales-manager`、`sales`、`ops`
- 核心场景：客户管理、订单审批、货源关联、跟进与时间线、账单与导出、AI 洞察

详细产品规则与角色约束请先阅读：[`AGENTS.md`](./AGENTS.md)（同内容也见 [`CLAUDE.md`](./CLAUDE.md)）。

## 主要能力（当前代码）

- **客户与生命周期**：客户档案、跟进记录、时间线、阶段流转与审批
- **订单与审批**：客户侧发起分配/订单，主管审批，支持批量场景
- **货源与云管同步**：货源以 cloudcost 为准，支持本地化同步（`cc_usage` / `cc_alert` / `cc_bill`）
- **账单中心**：本地账单聚合、按客户/按日下钻、CSV 导出、折扣计算器、账单同步
- **报表 BI（内嵌）**：作为账单中心 Tab，仅 `sales-manager` / `admin` / `root` 可见
- **销售管理看板**：主管视角 KPI、审批中心、团队目标相关指标
- **AI 洞察**：客户多源信息洞察（外部信息 + 本地销售数据）

## 技术栈

- 后端：FastAPI、SQLAlchemy 2、Alembic、PostgreSQL、Redis
- 前端：React 18、TypeScript、Vite 5、Ant Design 5、Recharts
- 认证：Casdoor OAuth2/OIDC（JWT）
- 部署：Docker、Azure Container Apps、Azure Static Web Apps
- 基础设施：Bicep（见 `infra/`）

## 快速开始（推荐 Docker）

1) 准备环境变量：

```bash
cp .env.example .env
```

2) 启动全部服务：

```bash
docker compose up --build
```

3) 访问地址：

- 前端：`http://localhost:5173`
- 后端 OpenAPI：`http://localhost:8000/docs`
- 健康检查：`http://localhost:8000/health`

## 本地开发（不使用 Docker）

后端：

```bash
pip install -r requirements.txt
alembic upgrade head
uvicorn main:app --reload
```

前端：

```bash
cd frontend
npm install
npm run dev
```

## 常用测试命令

```bash
# 后端单测
pytest -v

# 本地冒烟（需先启动 docker compose）
./scripts/smoke-test.sh
```

完整测试策略见 [`docs/TEST.md`](./docs/TEST.md)。

## API 分层（快速理解）

- `/api/*`：前端业务接口（Casdoor JWT）
- `/api/internal/*`：内部桥接/同步接口（M2M）
- `/api/external/*`：对 super-ops 暴露的只读接口（`X-Api-Key`）
- `/api/sync/cloudcost/*`：云管数据同步到本地表（受角色和 JWT 保护）

路由挂载可直接看 `main.py`。

## 前端路由（当前）

- 通用：`/login`、`/auth/callback`
- 销售主路径：`/home`、`/customers`、`/follow-ups`、`/resources`、`/allocations`、`/alerts`、`/bills`
- 主管路径：`/manager`（含团队/审批）、`/reports`（受角色保护）
- 兼容跳转：`/usage` 已重定向到 `/bills`

## 目录结构

```text
xiaoshou/
├── app/                  # FastAPI 业务代码（api/auth/models/schemas/agents）
├── frontend/             # React SPA（路由、页面、组件、鉴权上下文）
├── tests/                # pytest
├── docs/                 # 文档中心（产品、接口、部署、认证、测试）
├── infra/                # Azure Bicep IaC
├── docker-compose.yml    # 本地一键启动（postgres/redis/api/web）
├── Dockerfile            # 后端镜像
└── main.py               # 应用入口与路由挂载
```

## 文档入口

- 文档总索引：[`docs/README.md`](./docs/README.md)
- 云管对接：[`docs/CLOUDCOST_API.md`](./docs/CLOUDCOST_API.md)、[`docs/CLOUDCOST_AUTH.md`](./docs/CLOUDCOST_AUTH.md)
- 认证与角色：[`docs/AUTH.md`](./docs/AUTH.md)、[`docs/ROLES.md`](./docs/ROLES.md)、[`docs/SSO.md`](./docs/SSO.md)
- 部署：[`docs/DEPLOY.md`](./docs/DEPLOY.md)、[`infra/README.md`](./infra/README.md)
- 对外 API（super-ops）：[`docs/SUPER_OPS_API.md`](./docs/SUPER_OPS_API.md)

## 线上地址

- 前端：<https://purple-rock-072562e00.7.azurestaticapps.net>
- 后端：<https://xiaoshou-api.braveglacier-e1a32a70.eastasia.azurecontainerapps.io/docs>
