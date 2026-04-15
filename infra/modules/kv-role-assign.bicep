// Cross-RG role assignment: grants `Key Vault Secrets User` on an existing KV
// to the given principal (the UAMI from sales-rg).

param keyVaultName string

@description('Object ID of the principal (UAMI.properties.principalId).')
param principalId string

resource kv 'Microsoft.KeyVault/vaults@2023-07-01' existing = {
  name: keyVaultName
}

// Key Vault Secrets User = 4633458b-17de-408a-b874-0445c86b69e6
resource ra 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(kv.id, principalId, 'kv-secrets-user')
  scope: kv
  properties: {
    principalId: principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '4633458b-17de-408a-b874-0445c86b69e6')
  }
}
