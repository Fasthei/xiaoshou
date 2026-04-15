# Azure Infra — xiaoshou

Bicep 模板一键部署全部 Azure 资源。

## 资源清单与估算月成本（East Asia，Pay-As-You-Go 参考价）

| 资源 | SKU | 约价/月 (USD) | 用途 |
|---|---|---:|---|
| Azure Container Registry | Basic | ~$5 | 存 Docker 镜像 |
| Azure Container Apps | Consumption (0.5 vCPU/1 GiB, 1–5 副本) | ~$15–80 | 跑 FastAPI |
| Azure Database for PostgreSQL Flexible | Burstable B1ms + 32 GiB | ~$25 | 业务主库 |
| Azure Cache for Redis | Basic C0 (250 MB) | ~$16 | 缓存 |
| Azure Key Vault | Standard | <$1 | Casdoor secret、DB 密码 |
| Log Analytics + App Insights | PerGB2018, 30d 保留 | ~$5–20 | 日志/APM |
| Managed Identity | — | $0 | App → KV/ACR 无密钥访问 |
| **合计** | | **~$70–150** | |

> 生产建议：PG 升 `Standard_D2ds_v5`（~$130）+ HA，Redis 升 Standard C1（~$70）。

## 前置条件

- Azure CLI ≥ 2.60，`az login` 完成
- 订阅内已注册资源提供程序：`Microsoft.App`, `Microsoft.ContainerRegistry`, `Microsoft.DBforPostgreSQL`, `Microsoft.Cache`, `Microsoft.KeyVault`, `Microsoft.OperationalInsights`, `Microsoft.Insights`
- Casdoor 端已创建 Application（见 `docs/AUTH.md`），拿到 `client_id` / `client_secret`

## 部署

```bash
# 1. 创建资源组
RG=xiaoshou-prod-rg
az group create -n $RG -l eastasia

# 2. 修改 infra/main.parameters.json 填入真实密钥
# 3. 部署
az deployment group create \
  -g $RG \
  -f infra/main.bicep \
  -p @infra/main.parameters.json
```

## 首次部署后

Bicep 会用占位镜像（hello-world）先起一个 Container App。首次 CI/CD 成功后会替换为你的真实镜像。

输出里重点关注：
- `containerAppFqdn`  → 你的 API 公网地址
- `acrLoginServer`    → 给 CI 用
- `managedIdentityClientId` → 如需 OIDC 联邦凭据时使用

## 清理

```bash
az group delete -n xiaoshou-prod-rg --yes --no-wait
```
