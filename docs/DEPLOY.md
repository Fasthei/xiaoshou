# 部署指南（Azure）

> 目标：把 `xiaoshou` 部署到 Azure Container Apps，PostgreSQL / Redis / 密钥全部托管化，CI/CD 由 GitHub Actions 驱动。

## 整体架构

```
GitHub (push main)
   │  Actions: build → push → update revision
   ▼
Azure Container Registry (xiaoshouacr…) ──┐
                                          │ image pull (Managed Identity)
                                          ▼
Azure Container Apps  ◄── traffic ──  Public HTTPS
   │  env vars + secrets
   ├── Key Vault           (casdoor secret)
   ├── PostgreSQL Flex     (sales_system)
   ├── Azure Cache Redis   (session/hot cache)
   └── App Insights + Log Analytics (monitoring)
         │
         └── Casdoor (已有，eastasia) ── OIDC 发 JWT
```

## 一、首次部署（一次性操作）

### 1. 准备 Casdoor 应用

见 [AUTH.md](./AUTH.md)，拿到 `client_id` / `client_secret`。

### 2. 部署基础设施

```bash
# 登录并选择订阅
az login
az account set --subscription <SUBSCRIPTION_ID>

# 注册 Provider（只需一次）
for p in Microsoft.App Microsoft.ContainerRegistry Microsoft.DBforPostgreSQL \
         Microsoft.Cache Microsoft.KeyVault Microsoft.OperationalInsights \
         Microsoft.Insights Microsoft.ManagedIdentity; do
  az provider register -n $p
done

# 创建资源组
az group create -n xiaoshou-prod-rg -l eastasia

# 编辑 infra/main.parameters.json（PG 密码、Casdoor clientId/secret）
az deployment group create \
  -g xiaoshou-prod-rg \
  -f infra/main.bicep \
  -p @infra/main.parameters.json
```

记录输出：`acrName`、`containerAppFqdn`、`managedIdentityClientId`。

### 3. 配置 GitHub Actions OIDC 联邦凭据

```bash
SUB_ID=$(az account show --query id -o tsv)
APP_ID=$(az ad app create --display-name "xiaoshou-github-oidc" --query appId -o tsv)
az ad sp create --id $APP_ID

# 把订阅 Contributor 给这个 App（也可以更细粒度）
az role assignment create --assignee $APP_ID --role Contributor --scope /subscriptions/$SUB_ID

# 为 main 分支创建联邦凭据（把 <OWNER>/<REPO> 换成你的 repo）
cat > /tmp/fic.json <<EOF
{
  "name": "main-branch",
  "issuer": "https://token.actions.githubusercontent.com",
  "subject": "repo:<OWNER>/<REPO>:ref:refs/heads/main",
  "audiences": ["api://AzureADTokenExchange"]
}
EOF
az ad app federated-credential create --id $APP_ID --parameters @/tmp/fic.json

echo "AZURE_CLIENT_ID=$APP_ID"
echo "AZURE_TENANT_ID=$(az account show --query tenantId -o tsv)"
echo "AZURE_SUBSCRIPTION_ID=$SUB_ID"
```

### 4. 配置 GitHub 仓库 Secrets

仓库 → Settings → Secrets and variables → Actions → New repository secret：

- `AZURE_CLIENT_ID`
- `AZURE_TENANT_ID`
- `AZURE_SUBSCRIPTION_ID`

再编辑 `.github/workflows/deploy.yml` 把 `ACR_NAME: REPLACE_ME_...` 改成 bicep 输出的 `acrName`。提交。

### 5. 触发首次发布

```bash
git push origin main
```

Actions 会自动构建镜像、推 ACR、更新 Container App。成功后访问：

```
https://<containerAppFqdn>/docs
https://<containerAppFqdn>/api/auth/login   # 跳转 Casdoor
```

## 二、数据库初始化

首次部署时 Dockerfile 的 `CMD` 会自动执行 `alembic upgrade head`。若仓库里还没有生成迁移脚本：

```bash
# 本地执行一次（需要能连到 PG Flex，先临时开放你的出口 IP）
export DATABASE_URL="postgresql://sales_admin:<pw>@<pgFqdn>:5432/sales_system?sslmode=require"
alembic revision --autogenerate -m "initial"
alembic upgrade head
git add alembic/versions && git commit -m "db: initial migration" && git push
```

## 三、日常运维

- **查看日志**：`az containerapp logs show -g xiaoshou-prod-rg -n xiaoshou-api --follow`
- **滚动更新**：push 到 main 即自动
- **回滚**：`az containerapp revision list -g <rg> -n xiaoshou-api` → `activate` 旧 revision
- **扩缩容**：改 Bicep `scale.maxReplicas` 或用 `az containerapp update --max-replicas`
- **读写 Key Vault**：`az keyvault secret set -n casdoor-client-secret --vault-name <kv>`

## 四、成本优化

- 非生产环境：Container App `minReplicas: 0`（按需启动，可能有冷启动 ~2s）
- PG：`Burstable B1ms` 停机时能 stop（`az postgres flexible-server stop`）
- Redis：可用 App 本地 `fakeredis` 替代（改 `REDIS_URL`），省 $16/月
