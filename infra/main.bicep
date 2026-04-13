// ============================================================
// ハンズオンラボ用 Bicep テンプレート
// Foundry Agent Service + Foundry IQ KB + GitHub MCPTool (Remote MCP)
//
// リソース構成:
//   - Azure AI Services (Foundry — AOAI モデルを含む)
//   - Foundry Project (AI Services 直下 — Hub レス構成)
//   - Azure AI Search (Semantic Ranker 付き)
//   - Storage Account + Blob コンテナ (インシデントデータ格納)
//   - ワークスペース接続 (AI Search)
//   - ロール割り当て
//
// 設計ポイント:
//   Hub レス構成を採用。Microsoft.CognitiveServices/accounts/projects
//   リソースタイプで Project を AI Services 直下に作成する。
//   中間の AI Hub / Key Vault は不要。
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
var projectName = '${prefix}-project'

// ロール定義 ID
var storageBlobDataReaderRoleId = '2a2b9908-6ea1-4ae2-8e65-a410df84e7d1'
var cognitiveServicesOpenAIUserRoleId = '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd'
var searchIndexDataReaderRoleId = '1407120a-92aa-4202-b7e9-c0e197c71c8f'
var searchServiceContributorRoleId = '7ca78c08-252a-4471-8644-bb5ff32d4ba0'

// ------------------------------------------------------------
// Storage Account + Blob コンテナ (インシデントデータ格納用)
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
    disableLocalAuth: false
    authOptions: {
      aadOrApiKey: {
        aadAuthFailureMode: 'http401WithBearerChallenge'
      }
    }
  }
}

// ------------------------------------------------------------
// Azure AI Services (Foundry リソース — AOAI モデルを含む)
//
// kind: 'AIServices' は Azure OpenAI を含む統合 Cognitive Services
// リソース。Hub レス構成では、このリソースが Hub の役割を兼ね、
// Project が直下のサブリソースとして動作する。
// ------------------------------------------------------------
resource aiServices 'Microsoft.CognitiveServices/accounts@2025-12-01' = {
  name: take(aiServicesName, 64)
  location: aiServicesLocation
  kind: 'AIServices'
  sku: { name: aiServicesSku }
  identity: { type: 'SystemAssigned' }
  tags: {
    SecurityControl: 'Ignore'
  }
  properties: {
    customSubDomainName: take(aiServicesName, 64)
    publicNetworkAccess: 'Enabled'
    allowProjectManagement: true
  }
}

resource gpt4oDeployment 'Microsoft.CognitiveServices/accounts/deployments@2025-12-01' = {
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

resource embeddingDeployment 'Microsoft.CognitiveServices/accounts/deployments@2025-12-01' = {
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
// Foundry Project (AI Services 直下 — Hub レス構成)
//
// Microsoft.CognitiveServices/accounts/projects を使用し、
// AI Services の子リソースとして Project を作成する。
// AI Hub / Key Vault は不要。
// ------------------------------------------------------------
resource project 'Microsoft.CognitiveServices/accounts/projects@2025-04-01-preview' = {
  parent: aiServices
  name: projectName
  location: aiServicesLocation
  identity: { type: 'SystemAssigned' }
  tags: {
    SecurityControl: 'Ignore'
  }
  properties: {
    displayName: '${prefix} Agent Project'
  }
}

// AI Search 接続 (Project レベル)
resource projectSearchConnection 'Microsoft.CognitiveServices/accounts/projects/connections@2025-04-01-preview' = {
  parent: project
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
output projectName string = project.name
