# 认证集成（Casdoor）

本项目使用 [Casdoor](https://casdoor.org) 作为统一认证中心，走 OAuth2 Authorization Code + OIDC，后端以 JWT（RS256）做 API 保护。

现有 Casdoor 实例：
```
https://casdoor.ashyglacier-8207efd2.eastasia.azurecontainerapps.io
```

> ⚠️ 请**立即**将默认管理员密码 `By@123456` 修改为强密码（Casdoor 后台 → Users → admin → Reset password）。

## 一、在 Casdoor 里建 Application

1. 登录 Casdoor 后台 → **Applications** → **Add**
2. 关键字段：
   - **Name**：`xiaoshou`
   - **Organization**：`built-in`（或你新建的组织）
   - **Redirect URLs**：
     ```
     http://localhost:8000/api/auth/callback
     https://<containerAppFqdn>/api/auth/callback
     ```
   - **Token format**：`JWT`
   - **Token signing algorithm**：`RS256`
   - **Grant types**：至少勾选 `Authorization Code`、`Refresh Token`
3. 保存后记录 **Client ID** 与 **Client Secret**
4. 创建或分配用户，给予角色（后端会从 JWT `roles` 里读取）

## 二、后端如何校验

实现见 `app/auth/casdoor.py`：

1. 启动时从 `GET {casdoor}/api/get-cert?id={org}/{app}` 拉取应用公钥（PEM）
2. 每个受保护请求走 `HTTPBearer`，用 `python-jose` RS256 验签
3. 校验 `exp`、`aud=client_id`、`iss` 前缀等于 `CASDOOR_ENDPOINT`
4. 把 `sub / name / email / roles` 塞到 `CurrentUser`，通过 `Depends(require_auth)` 注入

**公共路由**：`/`、`/health`、`/api/auth/*`
**受保护路由**：其余所有 `/api/*`

## 三、前端/客户端调用方式

### 方案 A：完全后端驱动（推荐给 SSR / 小前端）

```
用户访问 https://<api>/api/auth/login
 → 302 跳 Casdoor 登录页
 → 登录后 Casdoor 302 回 /api/auth/callback?code=...
 → 后端用 code 换 access_token 返回 JSON
 → 前端保存 token，此后请求带 Authorization: Bearer <token>
```

### 方案 B：SPA 直连 Casdoor

前端使用 `casdoor-js-sdk` 或标准 OIDC 库（oidc-client-ts）跳转/拿 token，
后端只校验 token，不需要 `/api/auth/login`、`/api/auth/callback`。

## 四、调试

本地临时关掉认证：

```bash
export AUTH_ENABLED=false
```

此时所有 `/api/*` 放行，`/api/auth/me` 返回假用户 `dev`。**生产必须 `true`**。

## 五、用 curl 验证

```bash
# 拿 token（浏览器登录一次后从 /api/auth/callback 的响应里拿）
TOKEN=eyJhbGciOi...

curl -H "Authorization: Bearer $TOKEN" https://<fqdn>/api/auth/me
curl -H "Authorization: Bearer $TOKEN" https://<fqdn>/api/customers
```

## 六、角色与权限

当前实现只做 **是否登录** 的门槛。若要细化（例如仅 `sales` 角色能创建客户）：

```python
from fastapi import Depends, HTTPException
from app.auth import require_auth, CurrentUser

def require_sales(user: CurrentUser = Depends(require_auth)) -> CurrentUser:
    if not user.has_role("sales"):
        raise HTTPException(403, "sales role required")
    return user

@router.post("", dependencies=[Depends(require_sales)])
def create_customer(...): ...
```
