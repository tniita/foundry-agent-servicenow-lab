// ============================================================
// ハンズオンラボ用 Bicep テンプレート
// Foundry Agent Service + Foundry IQ KB + GitHub Function Tools
//
// リソース構成:
//   - Azure AI Services (統合 Cognitive Services — AOAI モデルを含む)
//   - Azure AI Search (Semantic Ranker 付き)
//   - Storage Account + Blob コンテナ (インシデントデータ格納)
//   - Key Vault (AI Hub 必須依存)
//   - AI Hub + AI Project (Foundry Agent Service のホスト)
//   - ワークスペース接続 (AI Search, AI Services)
//   - ロール割り当て
//
// 設計ポイント:
//   独立した Azure OpenAI リソースは作成しない。
//   Azure AI Services (kind: AIServices) が AOAI を含む統合リソースとなり、
//   AI Hub がこれを直接参照することで Foundry Project 内から
//   モデルデプロイ (gpt-4o, text-embedding-3-large) を利用できる。
//
// デプロイ:
//   az deployment group create \
//     --resource-group <rg-name> \
//     --template-file infra/main.bicep \
//     --parameters infra/main.bicepparam
// ============================================================

targetScope = 'resourceGroup'

// ------------------------------------------------------------
// パラメータ
// ------------------------------------------------------------
@description('リソースのプレフィックス名')
param prefix string = 'fiqlab'

@description('デプロイリージョン')
param location string = resourceGroup().location

@description('Azure AI Services のリージョン（モデル可用性に依存）')
param aiServicesLocation string = 'eastus2'

@description('Azure AI Search の SKU (Basic 以上が必要: Semantic Ranker)')
@allowed(['basic', 'standard', 'standard2'])
param searchSku string = 'basic'

@description('Azure AI Services の SKU')
@allowed(['S0'])
param aiServicesSku string = 'S0'

@description('GPT-4o モデルのデプロイ容量 (1K TPM 単位)')
param gpt4oCapacity int = 30

@description('Embedding モデルのデプロイ容量 (1K TPM 単位)')
param embeddingCapacity int = 120

@description('Blob コンテナ名（インシデントデータ格納用）')
param blobContainerName string = 'incidents'

// ------------------------------------------------------------
// 名前生成
// ------------------------------------------------------------
var uniqueSuffix = uniqueString(resourceGroup().id, prefix)
var searchName = '${prefix}-search-${uniqueSuffix}'
var aiServicesName = '${prefix}-ais-${uniqueSuffix}'
var storageName = replace('${prefix}st${uniqueSuffix}', '-', '')
var kvName = '${prefix}-kv-${uniqueSuffix}'
var hubName = '${prefix}-hub-${uniqueSuffix}'
var projectName = '${prefix}-project'

// ロール定義 ID
var storageBlobDataReaderRoleId = '2a2b9908-6ea1-4ae2-8e65-a410df84e7d1'
var cognitiveServicesOpenAIUserRoleId = '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd'
var searchIndexDataReaderRoleId = '1407120a-92aa-4202-b7e9-c0e197c71c8f'
var searchServiceContributorRoleId = '7ca78c08-252a-4471-8644-bb5ff32d4ba0'

// ------------------------------------------------------------
// Storage Account + Blob コンテナ
// ------------------------------------------------------------
resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: take(storageName, 24)
  location: location
  sku: { name: 'Standard_LRS' }
  kind: 'StorageV2'
  properties: {
    minimumTlsVersion: 'TLS1_2'
    supportsHttpsTrafficOnly: true
    allowBlobPublicAccess: false
  }
}

resource blobService 'Microsoft.Storage/storageAccounts/blobServices@2023-05-01' = {
  parent: storage
  name: 'default'
}

resource blobContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  parent: blobService
  name: blobContainerName
  properties: {
    publicAccess: 'None'
  }
}

// ------------------------------------------------------------
// Key Vault (AI Hub の必須依存)
// ------------------------------------------------------------
resource keyVault 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: take(kvName, 24)
  location: location
  properties: {
    tenantId: subscription().tenantId
    sku: { family: 'A', name: 'standard' }
    enableRbacAuthorization: true
    enableSoftDelete: true
    softDeleteRetentionInDays: 7
  }
}

// ------------------------------------------------------------
// Azure AI Search (Semantic Ranker 有効)
// ------------------------------------------------------------
resource search 'Microsoft.Search/searchServices@2024-06-01-preview' = {
  name: take(searchName, 60)
  location: location
  sku: { name: searchSku }
  identity: { type: 'SystemAssigned' }
  properties: {
    replicaCount: 1
    partitionCount: 1
    hostingMode: 'default'
    semanticSearch: 'standard'
  }
}

// ------------------------------------------------------------
// Azure AI Services (統合リソース — AOAI モデルを含む)
//
// kind: 'AIServices' は Azure OpenAI を含む統合 Cognitive Services
// リソース。独立した Azure OpenAI リソースは不要になり、
// Foundry Hub がこのリソースに直接接続してモデルを利用する。
// ------------------------------------------------------------
resource aiServices 'Microsoft.CognitiveServices/accounts@2024-10-01' = {
  name: take(aiServicesName, 64)
  location: aiServicesLocation
  kind: 'AIServices'
  sku: { name: aiServicesSku }
  identity: { type: 'SystemAssigned' }
  properties: {
    customSubDomainName: take(aiServicesName, 64)
    publicNetworkAccess: 'Enabled'
  }
}

resource gpt4oDeployment 'Microsoft.CognitiveServices/accounts/deployments@2024-10-01' = {
  parent: aiServices
  name: 'gpt-4o'
  sku: {
    name: 'GlobalStandard'
    capacity: gpt4oCapacity
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: 'gpt-4o'
      version: '2024-11-20'
    }
  }
}

resource embeddingDeployment 'Microsoft.CognitiveServices/accounts/deployments@2024-10-01' = {
  parent: aiServices
  name: 'text-embedding-3-large'
  sku: {
    name: 'Standard'
    capacity: embeddingCapacity
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: 'text-embedding-3-large'
      version: '1'
    }
  }
  dependsOn: [gpt4oDeployment]
}

// ------------------------------------------------------------
// AI Hub (Foundry Agent Service の親リソース)
//
// AI Hub は共有管理基盤（ガバナンスレイヤー）。
// 接続情報・セキュリティ設定を一元管理し、子 Project に継承する。
// Agent Service を利用するには Hub → Project の階層が必須。
// ------------------------------------------------------------
resource hub 'Microsoft.MachineLearningServices/workspaces@2024-10-01' = {
  name: take(hubName, 33)
  location: location
  kind: 'hub'
  identity: { type: 'SystemAssigned' }
  sku: { name: 'Basic', tier: 'Basic' }
  tags: {
    SecurityControl: 'Ignore'
  }
  properties: {
    friendlyName: '${prefix} AI Hub'
    storageAccount: storage.id
    keyVault: keyVault.id
    publicNetworkAccess: 'Enabled'
  }
  dependsOn: [blobContainer]
}

// AI Services 接続 (Hub レベル)
// Hub が AI Services に接続することで、配下の Project から
// gpt-4o / text-embedding-3-large を直接利用できる。
resource hubAIServicesConnection 'Microsoft.MachineLearningServices/workspaces/connections@2024-10-01' = {
  parent: hub
  name: 'aiservices-connection'
  properties: {
    authType: 'ApiKey'
    category: 'AIServices'
    isSharedToAll: true
    target: aiServices.properties.endpoint
    credentials: {
      key: aiServices.listKeys().key1
    }
    metadata: {
      ApiType: 'Azure'
      ResourceId: aiServices.id
    }
  }
}

// AI Search 接続 (Hub レベル)
resource hubSearchConnection 'Microsoft.MachineLearningServices/workspaces/connections@2024-10-01' = {
  parent: hub
  name: 'aisearch-connection'
  properties: {
    authType: 'ApiKey'
    category: 'CognitiveSearch'
    target: 'https://${search.name}.search.windows.net'
    credentials: {
      key: search.listAdminKeys().primaryKey
    }
    metadata: {
      ApiType: 'Azure'
      ResourceId: search.id
    }
  }
}

// ------------------------------------------------------------
// AI Project (Foundry Agent Service の実行環境)
//
// Hub の子リソース。Agent Service / KB がここで動作する。
// Hub の AI Services 接続・AI Search 接続を自動継承するため、
// Project 内から直接モデルデプロイを利用できる。
// ------------------------------------------------------------
resource project 'Microsoft.MachineLearningServices/workspaces@2024-10-01' = {
  name: projectName
  location: location
  kind: 'project'
  identity: { type: 'SystemAssigned' }
  sku: { name: 'Basic', tier: 'Basic' }
  tags: {
    SecurityControl: 'Ignore'
  }
  properties: {
    friendlyName: '${prefix} Agent Project'
    hubResourceId: hub.id
    publicNetworkAccess: 'Enabled'
  }
}

// ------------------------------------------------------------
// ロール割り当て
// ------------------------------------------------------------

// AI Search → Storage (Blob Data Reader) — KB がインシデントデータを読み取る
resource searchStorageRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: storage
  name: guid(storage.id, search.id, storageBlobDataReaderRoleId)
  properties: {
    principalId: search.identity.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', storageBlobDataReaderRoleId)
  }
}

// AI Search → AI Services (OpenAI User) — KB が Embedding/Chat モデルを使用
resource searchAIServicesRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: aiServices
  name: guid(aiServices.id, search.id, cognitiveServicesOpenAIUserRoleId)
  properties: {
    principalId: search.identity.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', cognitiveServicesOpenAIUserRoleId)
  }
}

// Project → AI Search (Index Data Reader) — Agent が KB を MCP 経由で読み取る
resource projectSearchReaderRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: search
  name: guid(search.id, project.id, searchIndexDataReaderRoleId)
  properties: {
    principalId: project.identity.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', searchIndexDataReaderRoleId)
  }
}

// Project → AI Search (Service Contributor) — Agent が MCP エンドポイントにアクセス
resource projectSearchContribRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: search
  name: guid(search.id, project.id, searchServiceContributorRoleId)
  properties: {
    principalId: project.identity.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', searchServiceContributorRoleId)
  }
}

// ------------------------------------------------------------
// 出力
// ------------------------------------------------------------
output searchEndpoint string = 'https://${search.name}.search.windows.net'
output searchName string = search.name
output aiServicesEndpoint string = aiServices.properties.endpoint
output aiServicesName string = aiServices.name
output storageAccountName string = storage.name
output blobContainerName string = blobContainerName
output storageConnectionString string = 'DefaultEndpointsProtocol=https;AccountName=${storage.name};EndpointSuffix=${environment().suffixes.storage};AccountKey=${storage.listKeys().keys[0].value}'
output projectEndpoint string = project.properties.discoveryUrl
output projectName string = project.name
output hubName string = hub.name
