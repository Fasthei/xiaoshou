// Azure infra for xiaoshou — Plan Y (reuse AuthData for shared data/secrets)
//
// This deployment runs in the NEW resource group `sales-rg` (eastasia).
// It CREATES: ACR, Log Analytics, App Insights, Container Apps Env, Container App, UAMI.
// It REUSES (cross-RG references to `AuthData`):
//   - PostgreSQL Flexible Server `dataope`   (database `sales_system` created out-of-band by CLI)
//   - Azure Cache for Redis     `oper`       (shared; xiaoshou uses database index 1)
//   - Azure Key Vault           `authoper`   (secrets for casdoor creds + PG password)
//
// Deploy:
//   az deployment group create -g sales-rg -f infra/main.bicep -p @infra/main.parameters.json

@description('Resource name prefix (3-10 lowercase letters/digits).')
param namePrefix string = 'xiaoshou'

@description('Azure region. Must match Casdoor (eastasia).')
param location string = resourceGroup().location

// ---- Reused resources (AuthData RG) ----
@description('Resource group of shared resources (PG, Redis, Key Vault).')
param sharedResourceGroup string = 'AuthData'

@description('Reused PostgreSQL Flexible Server name (in AuthData RG).')
param sharedPgServerName string = 'dataope'

@description('PostgreSQL admin login (existing).')
param sharedPgAdminUser string = 'dataope'

@description('Database name on the shared PG server (must already be created by CLI).')
param pgDatabaseName string = 'sales_system'

@description('Reused Redis cache name (in AuthData RG).')
param sharedRedisName string = 'oper'

@description('Redis db index to use (0 is likely used by Casdoor; pick 1 for xiaoshou).')
param redisDbIndex int = 1

@description('Reused Key Vault name (in AuthData RG).')
param sharedKeyVaultName string = 'authoper'

// ---- Secret names expected to already exist in the shared Key Vault ----
@description('KV secret name holding the PG admin password.')
param kvSecretPgPassword string = 'xiaoshou-pg-password'

@description('KV secret name holding Casdoor client secret for xiaoshou-app.')
param kvSecretCasdoorClientSecret string = 'xiaoshou-casdoor-client-secret'

// ---- Casdoor app config ----
@description('Casdoor endpoint.')
param casdoorEndpoint string = 'https://casdoor.ashyglacier-8207efd2.eastasia.azurecontainerapps.io'

@description('Casdoor organization.')
param casdoorOrg string = 'xingyun'

@description('Casdoor application name for this system.')
param casdoorAppName string = 'xiaoshou-app'

@description('Casdoor client id for xiaoshou-app.')
param casdoorClientId string

// ---- Container image ----
@description('Container image full ref (leave default for first deploy, CI updates later).')
param containerImage string = 'mcr.microsoft.com/azuredocs/containerapps-helloworld:latest'

var suffix = uniqueString(resourceGroup().id)
var acrName = toLower('${namePrefix}acr${suffix}')
var lawName = '${namePrefix}-law-${suffix}'
var aiName = '${namePrefix}-ai-${suffix}'
var caeName = '${namePrefix}-cae-${suffix}'
var appName = '${namePrefix}-api'
var uamiName = '${namePrefix}-uami-${suffix}'

// ---------- Cross-RG existing resources ----------
resource sharedPg 'Microsoft.DBforPostgreSQL/flexibleServers@2023-06-01-preview' existing = {
  name: sharedPgServerName
  scope: resourceGroup(sharedResourceGroup)
}

resource sharedRedis 'Microsoft.Cache/redis@2023-08-01' existing = {
  name: sharedRedisName
  scope: resourceGroup(sharedResourceGroup)
}

resource sharedKv 'Microsoft.KeyVault/vaults@2023-07-01' existing = {
  name: sharedKeyVaultName
  scope: resourceGroup(sharedResourceGroup)
}

// ---------- New resources in sales-rg ----------
resource law 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: lawName
  location: location
  properties: { sku: { name: 'PerGB2018' }, retentionInDays: 30 }
}

resource appInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: aiName
  location: location
  kind: 'web'
  properties: { Application_Type: 'web', WorkspaceResourceId: law.id }
}

resource acr 'Microsoft.ContainerRegistry/registries@2023-11-01-preview' = {
  name: acrName
  location: location
  sku: { name: 'Basic' }
  properties: { adminUserEnabled: false }
}

resource uami 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: uamiName
  location: location
}

// Grant UAMI: AcrPull on new ACR (same RG)
resource roleAcrPull 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(acr.id, uami.id, 'acr-pull')
  scope: acr
  properties: {
    principalId: uami.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '7f951dda-4ed3-4680-a7ca-43fe172d538d')
  }
}

// Grant UAMI: Key Vault Secrets User on shared KV (cross-RG via module)
module kvRoleAssign 'modules/kv-role-assign.bicep' = {
  name: 'kv-secrets-user-for-uami'
  scope: resourceGroup(sharedResourceGroup)
  params: {
    keyVaultName: sharedKeyVaultName
    principalId: uami.properties.principalId
  }
}

// ---------- Container Apps Environment ----------
resource cae 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: caeName
  location: location
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: law.properties.customerId
        sharedKey: law.listKeys().primarySharedKey
      }
    }
  }
}

// ---------- Container App ----------
resource containerApp 'Microsoft.App/containerApps@2024-03-01' = {
  name: appName
  location: location
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${uami.id}': {}
    }
  }
  properties: {
    managedEnvironmentId: cae.id
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: true
        targetPort: 8000
        transport: 'auto'
        allowInsecure: false
      }
      registries: [
        { server: acr.properties.loginServer, identity: uami.id }
      ]
      secrets: [
        {
          name: 'pg-password'
          keyVaultUrl: '${sharedKv.properties.vaultUri}secrets/${kvSecretPgPassword}'
          identity: uami.id
        }
        {
          name: 'casdoor-client-secret'
          keyVaultUrl: '${sharedKv.properties.vaultUri}secrets/${kvSecretCasdoorClientSecret}'
          identity: uami.id
        }
        { name: 'redis-key', value: sharedRedis.listKeys().primaryKey }
        { name: 'app-secret-key', value: uniqueString(resourceGroup().id, 'secret-key') }
      ]
    }
    template: {
      containers: [
        {
          name: 'api'
          image: containerImage
          resources: { cpu: json('0.5'), memory: '1Gi' }
          env: [
            // NOTE: DATABASE_URL/REDIS_URL are NOT set here because Container Apps
            // env values can't interpolate secretRef. We pass parts and let the
            // app (app/config.py) compose the URLs via effective_database_url /
            // effective_redis_url.
            { name: 'PG_USER', value: sharedPgAdminUser }
            { name: 'PG_HOST', value: sharedPg.properties.fullyQualifiedDomainName }
            { name: 'PG_DB', value: pgDatabaseName }
            { name: 'PG_PASSWORD', secretRef: 'pg-password' }
            // The app builds DATABASE_URL from the parts above (see app/config.py fallback).
            { name: 'REDIS_HOST', value: sharedRedis.properties.hostName }
            { name: 'REDIS_PASSWORD', secretRef: 'redis-key' }
            { name: 'REDIS_DB', value: string(redisDbIndex) }
            { name: 'SECRET_KEY', secretRef: 'app-secret-key' }
            { name: 'DEBUG', value: 'false' }
            { name: 'AUTH_ENABLED', value: 'true' }
            { name: 'CASDOOR_ENDPOINT', value: casdoorEndpoint }
            { name: 'CASDOOR_ORG', value: casdoorOrg }
            { name: 'CASDOOR_APP_NAME', value: casdoorAppName }
            { name: 'CASDOOR_CLIENT_ID', value: casdoorClientId }
            { name: 'CASDOOR_CLIENT_SECRET', secretRef: 'casdoor-client-secret' }
            { name: 'CORS_ORIGINS', value: '*' }
            { name: 'APPLICATIONINSIGHTS_CONNECTION_STRING', value: appInsights.properties.ConnectionString }
          ]
          probes: [
            { type: 'Liveness', httpGet: { path: '/health', port: 8000 }, initialDelaySeconds: 20, periodSeconds: 30 }
            { type: 'Readiness', httpGet: { path: '/health', port: 8000 }, initialDelaySeconds: 5, periodSeconds: 10 }
          ]
        }
      ]
      scale: {
        minReplicas: 1
        maxReplicas: 5
        rules: [ { name: 'http', http: { metadata: { concurrentRequests: '50' } } } ]
      }
    }
  }
  dependsOn: [ roleAcrPull, kvRoleAssign ]
}

// ---------- Outputs ----------
output acrLoginServer string = acr.properties.loginServer
output acrName string = acr.name
output containerAppName string = containerApp.name
output containerAppFqdn string = containerApp.properties.configuration.ingress.fqdn
output managedIdentityClientId string = uami.properties.clientId
output managedIdentityPrincipalId string = uami.properties.principalId
output sharedPgFqdn string = sharedPg.properties.fullyQualifiedDomainName
output sharedRedisHost string = sharedRedis.properties.hostName
output sharedKvUri string = sharedKv.properties.vaultUri
