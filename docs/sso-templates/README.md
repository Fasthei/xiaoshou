# SSO Templates — 跨系统复用包

> 本目录为销售 / 工单 / 运营中心 / 云管四系统统一认证的**可复用模板**。每个子目录对应一种语言栈，**复制整个子目录**到对应系统的 repo 即可。

| 系统 | 仓库 | 语言 | 用这个模板 |
|---|---|---|---|
| 销售 | `Fasthei/xiaoshou` | Python / FastAPI | 已内置（`app/auth/`） |
| 工单 | `Fasthei/gongdan` | TypeScript | [`typescript/`](./typescript/) |
| 运营中心 | ❓ | TypeScript？ | [`typescript/`](./typescript/) |
| 云管 | 外部 | Go / Java / ? | [`go/`](./go/) 或按本仓库验签约定自行实现 |

## 统一约定（所有语言都遵守）

- 一个 Casdoor Organization（示例 `xingyun`），一把 certificate 全组织共用（RS256）
- 每个系统独立的 Application → 独立 `client_id / client_secret / redirect_uri`
- 校验 JWT 时必做：`iss` 前缀 = Casdoor 域名、`aud` = 本系统 `client_id`、`exp` 未过期
- 角色统一用 [ROLES.md](../ROLES.md) 里的 9 个 code（`admin / sales / sales_manager / ops / ops_manager / finance / support / auditor / readonly`），不在代码里硬编码自定义角色
- `AUTH_ENABLED=false` 作为本地调试开关，生产必须 `true`

## 约定好处

- 用户在任一系统登录后，访问其他系统自动 SSO（Casdoor session cookie）
- 角色/组织变更在 Casdoor 一处操作即全域生效
- 代码模板一致 → 跨系统排查认证问题只需要看一处
