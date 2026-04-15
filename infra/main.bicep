// Azure infra for xiaoshou (FastAPI) — Container Apps + PG Flex + Redis + Key Vault + ACR
// Deploy:
//   az deployment group create -g <rg> -f infra/main.bicep -p @infra/main.parameters.json

@description('Resource name prefix (3-10 lowercase letters/digits).')
param namePrefix string = 'xiaoshou'

@description('Azure region (recommended: eastasia to co-locate with Casdoor).')
param location string = resourceGroup().location

@description('PostgreSQL admin login.')
param pgAdminUser string = 'sales_admin'

@secure()
@description('PostgreSQL admin password (≥12 chars, mixed case + digits).')
param pgAdminPassword string

@description('Casdoor endpoint (public URL).')
param casdoorEndpoint string = 'https://casdoor.ashyglacier-8207efd2.eastasia.azurecontainerapps.io'

@description('Casdoor application client id (from Casdoor console).')
param casdoorClientId string

@secure()
@description('Casdoor application client secret.')
param casdoorClientSecret string

@description('Casdoor organization.')
param casdoorOrg string = 'built-in'

@description('Casdoor application name.')
param casdoorAppName string = 'xiaoshou'

@description('Container image (full ref incl. tag). Leave default for first deploy.')
param containerImage string = 'mcr.microsoft.com/azuredocs/containerapps-helloworld:latest'

var suffix = uniqueString(resourceGroup().id)
var acrName = toLower('${namePrefix}acr${suffix}')
var lawName = '${namePrefix}-law-${suffix}'
var aiName = '${namePrefix}-ai-${suffix}'
var caeName = '${namePrefix}-cae-${suffix}'
var appName = '${namePrefix}-api'
var pgServerName = '${namePrefix}-pg-${suffix}'
var redisName = '${namePrefix}-redis-${suffix}'
var kvName = toLower('${namePrefix}kv${substring(suffix, 0, 8)}')

// ---------- Observability ----------
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

// ---------- Registry ----------
resource acr 'Microsoft.ContainerRegistry/registries@2023-11-01-preview' = {
  name: acrName
  location: location
  sku: { name: 'Basic' }
  properties: { adminUserEnabled: false }
}

// ---------- Managed Identity (app reads Key Vault + ACR) ----------
resource uami 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: '${namePrefix}-uami-${suffix}'
  location: location
}

// ---------- Key Vault ----------
resource kv 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: kvName
  location: location
  properties: {
    sku: { family: 'A', name: 'standard' }
    tenantId: subscription().tenantId
    enableRbacAuthorization: true
    enabledForTemplateDeployment: true
    publicNetworkAccess: 'Enabled'
  }
}

resource kvSecretPg 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: kv
  name: 'pg-admin-password'
  properties: { value: pgAdminPassword }
}

resource kvSecretCasdoor 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: kv
  name: 'casdoor-client-secret'
  properties: { value: casdoorClientSecret }
}

// Grant UAMI Key Vault Secrets User role
resource roleKvSecretsUser 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(kv.id, uami.id, 'kv-secrets-user')
  scope: kv
  properties: {
    principalId: uami.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '4633458b-17de-408a-b874-0445c86b69e6')
  }
}

// Grant UAMI AcrPull on ACR
resource roleAcrPull 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(acr.id, uami.id, 'acr-pull')
  scope: acr
  properties: {
    principalId: uami.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '7f951dda-4ed3-4680-a7ca-43fe172d538d')
  }
}

// ---------- PostgreSQL Flexible Server ----------
resource pg 'Microsoft.DBforPostgreSQL/flexibleServers@2023-06-01-preview' = {
  name: pgServerName
  location: location
  sku: { name: 'Standard_B1ms', tier: 'Burstable' }
  properties: {
    version: '16'
    administratorLogin: pgAdminUser
    administratorLoginPassword: pgAdminPassword
    storage: { storageSizeGB: 32 }
    backup: { backupRetentionDays: 7, geoRedundantBackup: 'Disabled' }
    highAvailability: { mode: 'Disabled' }
    network: { publicNetworkAccess: 'Enabled' }
  }
}

resource pgDb 'Microsoft.DBforPostgreSQL/flexibleServers/databases@2023-06-01-preview' = {
  parent: pg
  name: 'sales_system'
  properties: { charset: 'UTF8', collation: 'en_US.utf8' }
}

resource pgFwAzure 'Microsoft.DBforPostgreSQL/flexibleServers/firewallRules@2023-06-01-preview' = {
  parent: pg
  name: 'AllowAllAzureServices'
  properties: { startIpAddress: '0.0.0.0', endIpAddress: '0.0.0.0' }
}

// ---------- Redis ----------
resource redis 'Microsoft.Cache/redis@2023-08-01' = {
  name: redisName
  location: location
  properties: {
    sku: { name: 'Basic', family: 'C', capacity: 0 }
    enableNonSslPort: false
    minimumTlsVersion: '1.2'
  }
}

// ---------- Container Apps Environment + App ----------
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
        { name: 'database-url', value: 'postgresql://${pgAdminUser}:${pgAdminPassword}@${pg.properties.fullyQualifiedDomainName}:5432/sales_system?sslmode=require' }
        { name: 'redis-url', value: 'rediss://:${redis.listKeys().primaryKey}@${redis.properties.hostName}:6380/0' }
        { name: 'casdoor-client-secret', keyVaultUrl: '${kv.properties.vaultUri}secrets/casdoor-client-secret', identity: uami.id }
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
            { name: 'DATABASE_URL', secretRef: 'database-url' }
            { name: 'REDIS_URL', secretRef: 'redis-url' }
            { name: 'SECRET_KEY', secretRef: 'app-secret-key' }
            { name: 'DEBUG', value: 'false' }
            { name: 'AUTH_ENABLED', value: 'true' }
            { name: 'CASDOOR_ENDPOINT', value: casdoorEndpoint }
            { name: 'CASDOOR_CLIENT_ID', value: casdoorClientId }
            { name: 'CASDOOR_CLIENT_SECRET', secretRef: 'casdoor-client-secret' }
            { name: 'CASDOOR_ORG', value: casdoorOrg }
            { name: 'CASDOOR_APP_NAME', value: casdoorAppName }
            { name: 'CORS_ORIGINS', value: '*' }
            { name: 'APPLICATIONINSIGHTS_CONNECTION_STRING', value: appInsights.properties.ConnectionString }
          ]
          probes: [
            { type: 'Liveness', httpGet: { path: '/health', port: 8000 }, initialDelaySeconds: 20, periodSeconds: 30 }
            { type: 'Readiness', httpGet: { path: '/health', port: 8000 }, initialDelaySeconds: 5, periodSeconds: 10 }
          ]
        }
      ]
      scale: { minReplicas: 1, maxReplicas: 5, rules: [ { name: 'http', http: { metadata: { concurrentRequests: '50' } } } ] }
    }
  }
  dependsOn: [ roleAcrPull, roleKvSecretsUser ]
}

// ---------- Outputs ----------
output acrLoginServer string = acr.properties.loginServer
output acrName string = acr.name
output containerAppName string = containerApp.name
output containerAppFqdn string = containerApp.properties.configuration.ingress.fqdn
output pgFqdn string = pg.properties.fullyQualifiedDomainName
output redisHost string = redis.properties.hostName
output keyVaultName string = kv.name
output managedIdentityId string = uami.id
output managedIdentityClientId string = uami.properties.clientId
