# 统一认证设计（SSO across 4 Systems）

> 覆盖范围：**销售系统 (xiaoshou)** / **工单系统** / **超级运营中心** / **云管系统**
>
> 所有系统共用一套 Casdoor 账号、角色、权限，用户一次登录全站通行。

## 一、架构总览

```
                    ┌─────────────────────────────────────┐
                    │   Casdoor (单一身份源 / IdP)          │
                    │   https://casdoor.ashyglacier-…      │
                    │                                      │
                    │   Organization: xingyun  (示例)       │
                    │   Users   ← 共享                     │
                    │   Roles   ← 共享                     │
                    │   Groups  ← 共享                     │
                    │                                      │
                    │   Applications:                      │
                    │   ├── xiaoshou-app                   │
                    │   ├── ticket-app                     │
                    │   ├── opscenter-app                  │
                    │   └── cloudmgmt-app                  │
                    └──────────────┬──────────────────────┘
                                   │ OIDC (RS256 JWT)
                                   │ 同一把 cert 签发
        ┌──────────────┬───────────┼───────────┬──────────────┐
        ▼              ▼           ▼           ▼              ▼
  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐
  │ xiaoshou │  │  ticket  │  │ opscenter│  │ cloudmgmt│
  │ (FastAPI)│  │   (?)    │  │   (?)    │  │   (?)    │
  └──────────┘  └──────────┘  └──────────┘  └──────────┘
       │             │             │             │
       └─────────────┴─────────────┴─────────────┘
              同一段 auth 模块（见 §五）
              同一套 roles 判定（见 §三）
```

**核心原则**

1. **一个 Organization**：所有人在同一个 Casdoor org 下（用户表 / 角色表共享）。
2. **每个系统一个 Application**：不同 `client_id / client_secret / redirect_uri`，审计友好，便于单独下线。
3. **同一把签名证书**：Organization 级证书，Application 全部选同一把——**跨系统的 JWT 可互相校验**，但我们仍坚持各系统只信自己 `aud` 的 token（防止 token 挪用）。
4. **共享角色**：角色定义在 Organization 下，所有 Application 勾选"include roles in token"。

---

## 二、Casdoor 配置步骤

### 2.1 Organization

后台 → **Organizations** → **Add**
- **Name**：`xingyun`（或你自己的公司代号）
- **Display name**：星云销售运营平台
- **Account items**：勾选 `Email`、`Phone`、`Real name`、`Avatar`

### 2.2 Certificate（一把公用）

后台 → **Certificates** → **Add**
- **Name**：`cert-xingyun`
- **Owner**：`xingyun`
- **Type**：`x509`
- **Crypto algorithm**：`RS256`
- **Bit size**：2048
- 保存后，点 **View Certificate** 能拿到 PEM 公钥

### 2.3 四个 Application

每个系统建一个 Application，**Owner 都填 `xingyun`，Certificate 都选 `cert-xingyun`**。

| App Name | Redirect URLs | 用途 |
|---|---|---|
| `xiaoshou-app` | `http://localhost:8000/api/auth/callback`<br>`https://<xiaoshou-fqdn>/api/auth/callback` | 销售 |
| `ticket-app` | `https://<ticket-fqdn>/api/auth/callback` | 工单 |
| `opscenter-app` | `https://<opscenter-fqdn>/api/auth/callback` | 超级运营中心 |
| `cloudmgmt-app` | `https://<cloudmgmt-fqdn>/api/auth/callback` | 云管 |

公共字段：
- **Organization**：`xingyun`
- **Token format**：`JWT`
- **Token signing algorithm**：`RS256`
- **Token fields → include**：勾选 `roles`、`groups`、`permissions`、`email`、`phone`
- **Grant types**：勾选 `Authorization Code`、`Refresh Token`

保存后每个 App 得到独立的 `client_id` / `client_secret`。

---

## 三、共享角色定义（Role Catalog）

见 [ROLES.md](./ROLES.md)。

Casdoor 后台 → **Roles** → **Add**（Owner = `xingyun`）建好角色后：

- 在 **Users** 里把角色分配给具体用户
- 每个角色的 `Sub users / Sub roles` 可以嵌套（例如 `admin` 包含 `sales_manager`）

---

## 四、SSO 行为

### 4.1 Silent SSO（推荐前端方案）

用户已在 Casdoor 登录过，第二个系统跳登录时：
```
https://<app2>/api/auth/login
  → 302 到 Casdoor authorize
  → Casdoor 检测到 session cookie，直接 302 回 callback
  → 用户无感登录
```

**前提**：4 个系统共用**同一个 Casdoor 域名**，session cookie 在该域下。

### 4.2 Single Logout

调用 Casdoor 的 `/api/logout`，携带 `id_token_hint` 会广播注销到所有 Application。

---

## 五、复用代码：共享 auth 模块

`app/auth/` 目录在本仓库已实现，其他 3 个系统可**直接复制**或做成内部 pip 包。

### 5.1 Python 版（已在本仓库）

```
app/auth/
├── __init__.py
├── casdoor.py         # JWT 验签 + code 换 token
└── dependencies.py    # FastAPI 依赖：get_current_user / require_auth / require_role
```

**关键点**：
- 通过 `CASDOOR_APP_NAME` 区分系统，`aud` 校验只认本系统的 `client_id` → 防止 token 挪用
- `roles` 从 JWT 读取，**不写死在代码里**，4 个系统用同一份 `roles.py` 常量定义

### 5.2 其他语言已提供模板

**直接复制 `docs/sso-templates/<语言>/` 到对应系统仓库即可**：

| 语言 | 模板位置 | 适用系统 |
|---|---|---|
| TypeScript (jose + axios) | [`sso-templates/typescript/`](./sso-templates/typescript/) | 工单 `gongdan`、运营中心 |
| Go (golang-jwt/v5) | [`sso-templates/go/`](./sso-templates/go/) | 云管 |
| Python (python-jose) | 本仓库 `app/auth/` | 销售（本仓库）|

其他语言可参考模板自行实现，约定见 [`sso-templates/README.md`](./sso-templates/README.md)。

所有语言都遵循同样的约定：
- 向 `{CASDOOR}/api/get-cert?id=xingyun/<app-name>` 拿公钥
- 校验 `iss = {CASDOOR}`、`aud = <本系统 client_id>`、`exp`
- 把 `claims.roles` 当作权限源

### 5.3 Go 示例（给云管 / 工单参考）

```go
// auth/casdoor.go
package auth

import (
    "fmt"
    "github.com/golang-jwt/jwt/v5"
)

type Claims struct {
    Sub   string   `json:"sub"`
    Name  string   `json:"name"`
    Email string   `json:"email"`
    Owner string   `json:"owner"`
    Roles []string `json:"roles"`
    jwt.RegisteredClaims
}

func VerifyToken(tokenStr, pubKeyPEM, expectedAud, expectedIss string) (*Claims, error) {
    key, err := jwt.ParseRSAPublicKeyFromPEM([]byte(pubKeyPEM))
    if err != nil { return nil, err }

    tok, err := jwt.ParseWithClaims(tokenStr, &Claims{}, func(t *jwt.Token) (interface{}, error) {
        if t.Method.Alg() != "RS256" {
            return nil, fmt.Errorf("unexpected alg: %v", t.Header["alg"])
        }
        return key, nil
    },
        jwt.WithAudience(expectedAud),
        jwt.WithIssuer(expectedIss),
    )
    if err != nil || !tok.Valid { return nil, err }
    return tok.Claims.(*Claims), nil
}
```

---

## 六、同一会话跨系统跳转（给前端）

典型 UX：用户在"销售系统"看到某客户，点"查看工单" → 跳到"工单系统"同客户页。

- **A 方案（推荐）**：前端带上 access_token 到工单系统 `?access_token=...`，工单前端直接用它访问自家 API
- **B 方案**：跳转到工单系统登录入口，由 silent SSO 完成

两种方案都不需要重新输密码，因为底层 Casdoor session 已存在。

---

## 七、安全要点

| 项 | 做法 |
|---|---|
| token 泄露扩散 | 4 个 App 用**不同** `aud`，互相不接受对方 token |
| secret 管理 | 全部 `client_secret` 放各自系统的 Key Vault，不进代码仓库 |
| 证书轮换 | Casdoor 支持多证书，同时挂两把，逐步切换，各系统自动拉新的 |
| 离职用户 | Casdoor 禁用用户 → 所有系统下次刷新 token 时 401；强制下线可调 Casdoor `/api/logout` |
| 审计 | 所有登录/发 token 的日志在 Casdoor 一处看；业务操作日志各系统自己留 |

---

## 八、滚动落地建议

1. **Week 1**：先把本仓库（xiaoshou）接好 Casdoor，验证 JWT / SSO / 角色能通
2. **Week 2**：在 Casdoor 建另外 3 个 Application，把本仓库 `app/auth/*` 复制到工单系统（同为 Python/FastAPI）
3. **Week 3**：给云管（若 Go/Java）写同语言版本的 verify 函数，共用 `cert` 与 `roles`
4. **Week 4**：超级运营中心接入 + silent SSO 联调 + 统一登出
