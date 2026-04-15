# 销售系统 API (xiaoshou)

基于 FastAPI 开发的销售系统后端，部署到 **Azure Container Apps**，认证由 **Casdoor** 统一承担。

## 功能模块

- **客户管理**：客户主档、联系人管理、客户列表查询
- **货源管理**：货源池管理、可分配货源查询
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
- [`docs/AUTH.md`](docs/AUTH.md) — Casdoor 应用配置、JWT 校验原理
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
| `/api/resources/*` | **需 JWT** | 货源管理 |
| `/api/allocations/*` | **需 JWT** | 分配管理 |
| `/api/usage/*` | **需 JWT** | 用量查询 |

## 项目结构

```
xiaoshou/
├── app/
│   ├── api/                 # FastAPI 路由
│   ├── auth/                # Casdoor JWT 校验 & 依赖
│   ├── models/              # SQLAlchemy 模型
│   ├── schemas/             # Pydantic 模型
│   ├── config.py
│   └── database.py
├── infra/                   # Bicep IaC
├── docs/                    # 部署 / 认证文档
├── tests/                   # pytest
├── .github/workflows/       # CI + CD
├── Dockerfile
├── docker-compose.yml
├── main.py
└── requirements.txt
```

## 开发计划

- [x] 基础 CRUD（客户 / 货源 / 分配 / 用量）
- [x] Casdoor 认证接入
- [x] Azure 部署 (Bicep + Container Apps)
- [x] GitHub Actions CI/CD
- [ ] 角色细粒度授权
- [ ] 预警、CRM 商机、账单、Agent 分析

## License

MIT
