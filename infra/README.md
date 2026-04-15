# Azure Infra — xiaoshou（方案 Y：新 RG + 复用 AuthData 共享资源）

## 资源清单

### 新建在 `sales-rg`（本 Bicep 负责）

| 资源 | SKU | 月成本 |
|---|---|---:|
| Container Registry | Basic | ~$5 |
| Container Apps Env + App (0.5 vCPU/1 GiB, 1-5 副本) | Consumption | ~$15-80 |
| User-Assigned Managed Identity | — | $0 |
| Log Analytics + App Insights | PerGB2018 | ~$5 |

### 复用 `AuthData`

| 资源 | 名字 | 说明 |
|---|---|---|
| PostgreSQL Flex | `dataope` (Standard_B2s) | 在该实例上**新建** database `sales_system` |
| Redis Cache | `oper` (Basic) | 共用实例，xiaoshou 用 `db=1` |
| Key Vault | `authoper` | 存 `xiaoshou-pg-password` / `xiaoshou-casdoor-client-secret` |

**新增月成本估算：~$25–90**（比自建少 $40–60）

---

## 部署步骤

### 0. 前置

```bash
az login
az account set --subscription "Xmind运营学习专用2026"   # 或对应订阅

# （仅首次）注册 Provider
for p in Microsoft.App Microsoft.ContainerRegistry Microsoft.OperationalInsights \
         Microsoft.Insights Microsoft.ManagedIdentity; do
  az provider register -n $p
done
```

### 1. 在共享 PG 上建 `sales_system` 数据库

先把你**自己的出口 IP** 临时加白（或用 Azure Cloud Shell）：

```bash
MY_IP=$(curl -s ifconfig.me)
az postgres flexible-server firewall-rule create \
  -g AuthData -n dataope \
  --rule-name "tmp-$USER" --start-ip-address $MY_IP --end-ip-address $MY_IP

# 用 dataope 的 admin 账号连一次，建库（密码在 KV 或你本地）
PG_ADMIN_PW='<admin-password>'
PGPASSWORD="$PG_ADMIN_PW" psql \
  "host=dataope.postgres.database.azure.com port=5432 dbname=postgres user=dataope sslmode=require" \
  -c 'CREATE DATABASE sales_system;'
```

### 2. 把密钥写进共享 Key Vault `authoper`

```bash
# 给自己 KV 写权限（临时）
ME=$(az ad signed-in-user show --query id -o tsv)
KV_ID=$(az keyvault show -g AuthData -n authoper --query id -o tsv)
az role assignment create --assignee $ME --role "Key Vault Secrets Officer" --scope $KV_ID

# 写两条 secret
az keyvault secret set --vault-name authoper -n xiaoshou-pg-password           --value "$PG_ADMIN_PW"
az keyvault secret set --vault-name authoper -n xiaoshou-casdoor-client-secret --value "<casdoor-client-secret>"
```

### 3. 在 Casdoor 建 `xiaoshou-app` Application

Casdoor 后台 → Applications → Add，参考 `../docs/SSO.md §2.3`。
拿到 `client_id`，填到 `infra/main.parameters.json` 的 `casdoorClientId`。

### 4. 建 RG 并部署

```bash
az group create -n sales-rg -l eastasia

az deployment group create \
  -g sales-rg \
  -f infra/main.bicep \
  -p @infra/main.parameters.json
```

部署约 5-8 分钟。输出里记录：
- `acrName` → 填进 `.github/workflows/deploy.yml`
- `containerAppFqdn` → 回到 Casdoor 后台把这个 FQDN 加到 `xiaoshou-app` 的 Redirect URLs

### 5. 配置 GitHub Actions（见 `../docs/DEPLOY.md §3-5`）

只是把 `RESOURCE_GROUP: xiaoshou-prod-rg` 改成 `RESOURCE_GROUP: sales-rg`。

---

## 清理

```bash
# 只删 sales-rg（共享资源不会动）
az group delete -n sales-rg --yes --no-wait

# 清理加在 AuthData 里的东西（可选）
az keyvault secret delete --vault-name authoper -n xiaoshou-pg-password
az keyvault secret delete --vault-name authoper -n xiaoshou-casdoor-client-secret
# 在 dataope 上 DROP DATABASE sales_system;
```
