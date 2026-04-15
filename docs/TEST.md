# 测试方案

分三层：**单元测试 / 本地端到端 / 部署后冒烟 + 认证端到端**。

## 一、单元测试（CI 自动运行）

**位置**：`tests/`

| 文件 | 覆盖点 |
|---|---|
| `test_health.py` | `/`、`/health`、`AUTH_ENABLED=false` 时的 dev 模式 `/api/auth/me` |
| `test_config.py` | `effective_database_url`、`effective_redis_url` 的 URL 拼接；`CORS_ORIGINS` 解析 |
| `test_auth.py` | 无 token → 401；伪造 `verify_jwt` 返回 claims → `/api/auth/me` 200；过期 token → 401 |

**运行**：

```bash
pip install -r requirements.txt pytest
pytest -v
```

GitHub Actions `ci.yml` 每次 push / PR 都会跑，Python 3.11。

## 二、本地集成测试（需 docker）

```bash
cp .env.example .env
# 编辑 .env 填 Casdoor client_id / secret

docker compose up --build -d
./scripts/smoke-test.sh
# 期望：所有 public/未授权 check 通过；auth 流程走 302

# 用浏览器完整走一次 OAuth2 流程
open http://localhost:8000/api/auth/login
# 登录后 callback 返回 token，拷出来
TOKEN=<paste> BASE_URL=http://localhost:8000 ./scripts/smoke-test.sh
# 期望：所有 5/5 section 全绿
```

## 三、部署后测试

### 3.1 冒烟（无登录）

```bash
FQDN=$(az containerapp show -g sales-rg -n xiaoshou-api \
  --query properties.configuration.ingress.fqdn -o tsv)
BASE_URL=https://$FQDN ./scripts/smoke-test.sh
```

**验收标准**（4/5 通过，section 5 跳过）：
- `/` 200、`/health` 200、`/docs` 200
- `/api/customers` 未带 token → **401**（证明认证已启用，这是关键）
- `/api/auth/login` → 307 重定向到 Casdoor

### 3.2 跨 RG 连通性

```bash
# 查看最近日志，确认启动期没有 DB/Redis 连接失败
az containerapp logs show -g sales-rg -n xiaoshou-api --tail 100 --follow=false | \
  grep -Ei 'error|failed|refused|timeout' || echo "clean"
```

**期望**：无 `could not connect to server`、无 `redis.exceptions.ConnectionError`、无 KeyVault 403。

若看到 `Access denied`：说明 UAMI 的 KV Secrets User 角色还没生效，等 1-2 分钟重试（AAD 传播延迟）。

### 3.3 认证端到端（手动一次性）

**浏览器步骤**：

1. 打开 `https://<fqdn>/api/auth/login`
2. 跳转到 Casdoor 登录页，输入测试用户
3. Casdoor 302 回 `https://<fqdn>/api/auth/callback?code=...`
4. **预期响应**（JSON）：
   ```json
   {
     "access_token": "eyJ...",
     "id_token": "eyJ...",
     "refresh_token": "...",
     "token_type": "Bearer",
     "expires_in": 168480
   }
   ```

5. 拷 `access_token`，命令行：
   ```bash
   TOKEN="eyJ..."
   BASE_URL="https://<fqdn>"

   # /me 返回用户信息
   curl -H "Authorization: Bearer $TOKEN" $BASE_URL/api/auth/me
   # 预期：{"sub": "...", "name": "...", "roles": [...]}

   # 带 token 访问业务接口
   curl -H "Authorization: Bearer $TOKEN" "$BASE_URL/api/customers?page=1"
   # 预期：{"total": 0, "items": []}  (空库但鉴权通过)
   ```

### 3.4 角色校验测试（需要在 Casdoor 为测试用户授不同角色）

```bash
# 准备两个用户：alice (sales), bob (readonly)
# bob 尝试创建客户应 403（如果用了 require_roles("sales", "admin")）
curl -X POST -H "Authorization: Bearer $BOB_TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"customer_code":"T001","customer_name":"测试","customer_status":"active"}' \
     $BASE_URL/api/customers
# 当前代码只要求登录 (require_auth)，所以 bob 也能创建。
# 若把路由改为 Depends(require_roles("sales","admin"))，则期望 403
```

### 3.5 负载 / 扩缩容（可选）

```bash
# 用 hey 或 ab 压一下，看 Container Apps 自动扩副本
hey -z 60s -c 50 -H "Authorization: Bearer $TOKEN" $BASE_URL/api/auth/me

az containerapp revision list -g sales-rg -n xiaoshou-api \
  --query "[].{name:name, replicas:properties.replicas, active:properties.active}" -o table
```

**期望**：`replicas` 从 1 扩到 2-3，压力停掉后 5-10 分钟回落。

## 四、验收清单（部署完成后对照勾选）

- [ ] `ci.yml` 最近一次运行全绿
- [ ] `smoke-test.sh` 无 token 版本 4/5 通过
- [ ] Container App 启动日志无 DB/Redis/KV 报错
- [ ] 浏览器能完整走完 Casdoor 登录 → callback → 拿 token
- [ ] `curl /api/auth/me` 带 token 返回用户信息
- [ ] `curl /api/customers` 带 token 返回 200
- [ ] `curl /api/customers` 不带 token 返回 401
- [ ] App Insights 能看到请求追踪（需要在代码里接 `OpenTelemetry`/`opencensus`——非本次范围，后续补）

## 五、常见失败与排查

| 症状 | 可能原因 | 排查命令 |
|---|---|---|
| App 启动 CrashLoopBackOff | DB 连不上（密码/防火墙） | `az containerapp logs show ... \| grep -i psycopg` |
| 401 `invalid token` (有 token) | iss/aud 不匹配 | 解码 JWT 看 `aud`；与 `CASDOOR_CLIENT_ID` 对比 |
| `/api/auth/login` 跳转后报 `redirect_uri mismatch` | Casdoor 应用没加入本 FQDN | Casdoor 后台 → xiaoshou-app → Redirect URLs 加一行 |
| KV `Forbidden` | UAMI 角色未生效 | `az role assignment list --assignee <uami-principal-id> --all` |
| `DATABASE_URL not configured` | PG_* 没注入 | `az containerapp show ... --query 'properties.template.containers[0].env'` 核查 |
