# xiaoshou — Frontend (React + Vite + Antd)

SPA for 销售系统，与 `gongdan/ticket-system/frontend` 技术栈一致：Vite 5 + React 18 + TS 5 + Ant Design 5。

## 开发

```bash
cp .env.example .env
# 编辑 .env 填好 VITE_API_BASE / VITE_CASDOOR_CLIENT_ID / VITE_CASDOOR_REDIRECT

npm install
npm run dev
# 访问 http://localhost:5173
```

**首次登录前**，需要在 Casdoor 后台的 `operation/sales` 应用 Redirect URIs 里添加：

- 开发：`http://localhost:5173/auth/callback`
- 生产：`https://<swa-fqdn>/auth/callback`

## 构建 & 预览

```bash
npm run build    # 产物在 dist/
npm run preview
```

## 部署（Azure Static Web Apps）

由 `.github/workflows/frontend-deploy.yml` 自动处理。需要在 GitHub Actions Secret 里配置：

- `AZURE_STATIC_WEB_APPS_API_TOKEN`  (SWA 的 deployment token)
- `VITE_API_BASE`                    (后端 FQDN)
- `VITE_CASDOOR_CLIENT_ID`
- `VITE_CASDOOR_REDIRECT`

## 页面

| 路由 | 功能 |
|---|---|
| `/login` | Casdoor 登录入口 |
| `/auth/callback` | OAuth2 回调，交换 code → token |
| `/customers` | 客户管理（列表 + 新建 + 编辑） |
| `/resources` | 货源管理（筛选 + 列表） |
| `/allocations` | 分配管理（列表 + 毛利） |
| `/usage` | 用量查询（按客户汇总 + 明细） |

## 认证机制

1. 用户点"使用 Casdoor 登录" → 前端跳 `https://<casdoor>/login/oauth/authorize?...`
2. Casdoor 登录后 302 回 `https://<this-app>/auth/callback?code=...`
3. 前端把 code 传给后端 `GET /api/auth/callback`，后端用 client_secret 换 token 返回
4. 前端存 `xs_token` 到 localStorage，调 `/api/auth/me` 拿用户信息
5. 后续请求经 axios interceptor 自动加 `Authorization: Bearer <token>`
6. 收到 401 → 清 token → 跳 `/login`
