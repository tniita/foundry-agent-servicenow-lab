using 'main.bicep'

// ============================================================
// パラメータ値
// 必要に応じてプレフィックス・リージョン・SKU を変更してください
// ============================================================

param prefix = 'fiqlab'
param location = 'japaneast'
param aiServicesLocation = 'eastus2'  // GPT-4o / Embedding の可用リージョン
param searchSku = 'basic'             // Semantic Ranker は Basic 以上で利用可
param aiServicesSku = 'S0'
param gpt4oCapacity = 30              // 30K TPM
param embeddingCapacity = 120          // 120K TPM
param blobContainerName = 'incidents'
