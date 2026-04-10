"""設定管理 — 環境変数から各サービスの接続情報を読み込む."""

import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class AzureSearchConfig:
    """Azure AI Search の接続設定."""
    endpoint: str = os.getenv("AZURE_SEARCH_ENDPOINT", "")
    api_key: str = os.getenv("AZURE_SEARCH_API_KEY", "")


@dataclass(frozen=True)
class BlobStorageConfig:
    """Azure Blob Storage の接続設定（インシデントデータ格納）."""
    connection_string: str = os.getenv("BLOB_CONNECTION_STRING", "")
    container_name: str = os.getenv("BLOB_CONTAINER_NAME", "incidents")


@dataclass(frozen=True)
class FoundryIQConfig:
    """Foundry IQ ナレッジベース設定."""
    search_endpoint: str = os.getenv("AZURE_SEARCH_ENDPOINT", "")
    search_api_key: str = os.getenv("AZURE_SEARCH_API_KEY", "")
    knowledge_base_name: str = os.getenv("FOUNDRY_IQ_KNOWLEDGE_BASE_NAME", "system-inquiry-kb")
    knowledge_source_name: str = os.getenv("FOUNDRY_IQ_KNOWLEDGE_SOURCE_NAME", "incidents-blob-ks")


@dataclass(frozen=True)
class AzureOpenAIConfig:
    """Azure OpenAI Service の接続設定."""
    endpoint: str = os.getenv("AZURE_OPENAI_ENDPOINT", "")
    api_key: str = os.getenv("AZURE_OPENAI_API_KEY", "")
    api_version: str = os.getenv("AZURE_OPENAI_API_VERSION", "2024-12-01-preview")
    chat_deployment: str = os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT", "gpt-4o")
    embedding_deployment: str = os.getenv(
        "AZURE_OPENAI_EMBEDDING_DEPLOYMENT", "text-embedding-3-large"
    )


@dataclass(frozen=True)
class ProjectConfig:
    """Foundry Agent Service プロジェクト設定."""
    endpoint: str = os.getenv("PROJECT_ENDPOINT", "")
    connection_name: str = os.getenv("PROJECT_CONNECTION_NAME", "kb-mcp-connection")
    agent_name: str = os.getenv("AGENT_NAME", "system-inquiry-agent")
    model_deployment: str = os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT", "gpt-4o")


@dataclass(frozen=True)
class GitHubConfig:
    """GitHub リポジトリの接続設定（Function Tool が使用）."""
    token: str = os.getenv("GITHUB_TOKEN", "")
    owner: str = os.getenv("GITHUB_OWNER", "")
    repo: str = os.getenv("GITHUB_REPO", "")
    branch: str = os.getenv("GITHUB_BRANCH", "main")


search_cfg = AzureSearchConfig()
blob_cfg = BlobStorageConfig()
foundry_iq_cfg = FoundryIQConfig()
openai_cfg = AzureOpenAIConfig()
project_cfg = ProjectConfig()
github_cfg = GitHubConfig()
