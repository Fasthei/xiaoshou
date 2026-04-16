# 销售系统 API (xiaoshou)

基于 FastAPI 开发的销售系统后端，部署到 **Azure Container Apps**，认证由 **Casdoor** 统一承担。

## 功能模块

- **客户管理**：客户主档、联系人管理、客户列表查询
- **货源看板**：货源池管理、可分配货源查询
- **分配管理**：货源分配、毛利计算
- **用量查询**：客户用量、用量趋势、用量汇总

## 技术栈

- **框架**：FastAPI 0.109
- **数据库**：PostgreSQL 16 + SQLAlchemy 2
- **缓存**：Redis 7
- **认证**：Casdoor OAuth2 / OIDC (RS256 JWT)
- **容器**：Docker → Azure Container Apps
- **CI/CD**：GitHub Actions (OIDC 到 Azure)
- **IaC**：Bicep (`infra/main.bicep`)

## 快速开始（本地）

```bash
cp .env.example .env
# 编辑 .env：填 Casdoor client_id / secret；或临时 AUTH_ENABLED=false 跳过认证

docker compose up --build
# 访问 http://localhost:8000/docs
```

不用 Docker：

```bash
pip install -r requirements.txt
alembic upgrade head
uvicorn main:app --reload
```

## 部署到 Azure

详见：
- [`docs/DEPLOY.md`](docs/DEPLOY.md) — 资源开通、CI/CD OIDC、发布流程
- [`docs/AUTH.md`](docs/AUTH.md) — 本系统 Casdoor 接入细节
- [`docs/SSO.md`](docs/SSO.md) — **跨系统（销售/工单/运营中心/云管）统一认证架构**
- [`docs/ROLES.md`](docs/ROLES.md) — **共享角色定义**
- [`docs/TEST.md`](docs/TEST.md) — **测试方案（单元 / 集成 / 部署后冒烟 / 认证 E2E）**
- [`infra/README.md`](infra/README.md) — Bicep 资源清单 + 月成本估算

## API 路由

| 路由 | 认证 | 说明 |
|---|---|---|
| `GET /` | 公开 | 欢迎信息 |
| `GET /health` | 公开 | 健康检查 |
| `GET /api/auth/login` | 公开 | 跳转 Casdoor 登录 |
| `GET /api/auth/callback` | 公开 | OAuth2 回调，换 token |
| `GET /api/auth/me` | **需 JWT** | 当前用户信息 |
| `/api/customers/*` | **需 JWT** | 客户管理 |
| `/api/resources/*` | **需 JWT** | 货源看板 |
| `/api/allocations/*` | **需 JWT** | 分配管理 |
| `/api/usage/*` | **需 JWT** | 用量查询 |

## 项目结构

```
xiaoshou/
├── app/                     # FastAPI 后端
│   ├── api/                 # 路由
│   ├── auth/                # Casdoor JWT 校验 & 依赖
│   ├── models/              # SQLAlchemy 模型
│   ├── schemas/             # Pydantic 模型
│   ├── config.py
│   └── database.py
├── frontend/                # React + Vite + Antd SPA
│   ├── src/
│   │   ├── api/             # axios + interceptor
│   │   ├── components/      # 布局 / 路由守卫
│   │   ├── contexts/        # AuthContext
│   │   ├── config/          # Casdoor 配置
│   │   ├── pages/           # Login / Callback / Customers / Resources / Allocations / Usage
│   │   └── types/
│   └── staticwebapp.config.json
├── infra/                   # Bicep IaC
├── docs/                    # 部署 / 认证 / SSO / 角色 / 测试
├── tests/                   # pytest
├── .github/workflows/       # ci.yml (后端测试) + deploy.yml (后端 Container App) + frontend-deploy.yml (SWA)
├── Dockerfile
├── docker-compose.yml
├── main.py
└── requirements.txt
```

## 在线地址

- 后端 API：https://xiaoshou-api.braveglacier-e1a32a70.eastasia.azurecontainerapps.io/docs
- 前端 SPA：https://purple-rock-072562e00.7.azurestaticapps.net

## 开发计划

- [x] 基础 CRUD（客户 / 货源 / 分配 / 用量）
- [x] Casdoor 认证接入
- [x] Azure 部署 (Bicep + Container Apps)
- [x] GitHub Actions CI/CD
- [ ] 角色细粒度授权
- [ ] 预警、CRM 商机、账单、Agent 分析

## License

MIT
