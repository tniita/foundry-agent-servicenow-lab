"""Foundry Agent Service エージェントセットアップ.

プロジェクト接続 (KB MCP + GitHub MCP) と Prompt Agent を作成する。
Bicep デプロイと setup_knowledge.py 実行後に一度だけ実行する。

使用法:
    python -m scripts.setup_agent
"""

from __future__ import annotations

import argparse
import logging
import os
import sys

import requests
from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import MCPTool, PromptAgentDefinition
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# プロジェクト接続名
GITHUB_CONNECTION_NAME = "GitHub"


def get_config():
    """環境変数から設定を取得する."""
    required = {
        "PROJECT_ENDPOINT": os.getenv("PROJECT_ENDPOINT", ""),
        "AZURE_SEARCH_ENDPOINT": os.getenv("AZURE_SEARCH_ENDPOINT", ""),
        "FOUNDRY_IQ_KNOWLEDGE_BASE_NAME": os.getenv("FOUNDRY_IQ_KNOWLEDGE_BASE_NAME", "system-inquiry-kb"),
        "PROJECT_CONNECTION_NAME": os.getenv("PROJECT_CONNECTION_NAME", "kb-mcp-connection"),
        "AGENT_NAME": os.getenv("AGENT_NAME", "system-inquiry-agent"),
        "AZURE_OPENAI_CHAT_DEPLOYMENT": os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT", "gpt-4o"),
        "GITHUB_TOKEN": os.getenv("GITHUB_TOKEN", ""),
        "GITHUB_OWNER": os.getenv("GITHUB_OWNER", ""),
        "GITHUB_REPO": os.getenv("GITHUB_REPO", ""),
    }
    missing = [k for k, v in required.items() if not v]
    if missing:
        logger.error("環境変数が未設定: %s", ", ".join(missing))
        sys.exit(1)
    return required


def _put_connection(
    project_resource_id: str,
    bearer_token_provider,
    connection_name: str,
    body: dict,
) -> None:
    """プロジェクト接続を PUT (作成 or 更新) する."""
    response = requests.put(
        f"https://management.azure.com{project_resource_id}"
        f"/connections/{connection_name}?api-version=2025-04-01-preview",
        headers={"Authorization": f"Bearer {bearer_token_provider()}"},
        json=body,
        timeout=60,
    )
    response.raise_for_status()
    logger.info("✅ プロジェクト接続 '%s' を作成しました", connection_name)


def create_project_connections(cfg: dict) -> None:
    """プロジェクト接続を作成する (KB MCP + GitHub MCP).

    Hub レス構成では Project は Microsoft.CognitiveServices/accounts/projects
    リソースとして作成されるため、接続も同リソースの子リソースとして作成する。
    """
    project_resource_id = os.getenv("PROJECT_RESOURCE_ID", "")
    if not project_resource_id:
        logger.warning(
            "PROJECT_RESOURCE_ID が未設定です。接続の作成をスキップします。"
        )
        return

    credential = DefaultAzureCredential()
    bearer_token_provider = get_bearer_token_provider(
        credential, "https://management.azure.com/.default"
    )

    # 1. KB MCP 接続 (Foundry IQ ナレッジベース)
    search_endpoint = cfg["AZURE_SEARCH_ENDPOINT"]
    kb_name = cfg["FOUNDRY_IQ_KNOWLEDGE_BASE_NAME"]
    kb_connection_name = cfg["PROJECT_CONNECTION_NAME"]
    mcp_endpoint = (
        f"{search_endpoint}/knowledgebases/{kb_name}/mcp"
        f"?api-version=2025-11-01-preview"
    )

    _put_connection(
        project_resource_id,
        bearer_token_provider,
        kb_connection_name,
        {
            "name": kb_connection_name,
            "properties": {
                "authType": "ProjectManagedIdentity",
                "category": "RemoteTool",
                "target": mcp_endpoint,
                "isSharedToAll": True,
                "audience": "https://search.azure.com/",
                "metadata": {"ApiType": "Azure"},
            },
        },
    )

    # 2. GitHub MCP 接続 (GitHub リモート MCP サーバー — カタログツール形式)
    github_token = cfg["GITHUB_TOKEN"]
    _put_connection(
        project_resource_id,
        bearer_token_provider,
        GITHUB_CONNECTION_NAME,
        {
            "name": GITHUB_CONNECTION_NAME,
            "properties": {
                "authType": "CustomKeys",
                "category": "RemoteTool",
                "target": "https://api.githubcopilot.com/mcp",
                "isSharedToAll": True,
                "credentials": {
                    "keys": {
                        "Authorization": f"Bearer {github_token}",
                    },
                },
                "metadata": {"ApiType": "GitHub"},
            },
        },
    )


def create_agent(cfg: dict) -> None:
    """Prompt Agent を作成する（KB MCPTool + GitHub MCPTool）.

    両ツールとも Foundry Agent Service のネイティブ MCPTool として登録し、
    サーバーサイドで自動実行される。クライアント側の dispatch は不要。
    """
    credential = DefaultAzureCredential()
    project_client = AIProjectClient(
        endpoint=cfg["PROJECT_ENDPOINT"],
        credential=credential,
    )

    search_endpoint = cfg["AZURE_SEARCH_ENDPOINT"]
    kb_name = cfg["FOUNDRY_IQ_KNOWLEDGE_BASE_NAME"]
    kb_connection_name = cfg["PROJECT_CONNECTION_NAME"]
    agent_name = cfg["AGENT_NAME"]
    model = cfg["AZURE_OPENAI_CHAT_DEPLOYMENT"]
    github_owner = cfg["GITHUB_OWNER"]
    github_repo = cfg["GITHUB_REPO"]

    mcp_endpoint = (
        f"{search_endpoint}/knowledgebases/{kb_name}/mcp"
        f"?api-version=2025-11-01-preview"
    )

    instructions = f"""\
あなたは社内 IT システムの問い合わせ対応エージェントです。
以下の情報ソースを活用してユーザーの質問に回答します。

1. **インシデント情報**（Foundry IQ ナレッジベース）
   - ServiceNow に登録された過去のインシデント（障害、不具合、問い合わせ）
   - knowledge_base_retrieve ツール（MCP）で自動検索

2. **ソースコード・設計書**（GitHub リポジトリ）
   - GitHub MCP ツールで取得（get_file_contents, search_code 等）
   - 対象リポジトリ: owner="{github_owner}", repo="{github_repo}"

## 回答方針
- 質問の内容に応じて適切なツールを選択・組み合わせてください
- ナレッジベースからの情報には引用（annotation）を付与してください
- コードや設計書の該当箇所はファイルパスと内容を引用してください
- 不確かな情報は「確認中」と明記し、推測は推測と表記してください
- 回答は日本語で、構造化された形式で返してください
- ナレッジベースに回答がない場合は「該当する情報が見つかりませんでした」と回答してください
- GitHub ツールを使う際は owner="{github_owner}", repo="{github_repo}" を指定してください
"""

    # MCPTool 1: Foundry IQ KB への接続
    mcp_kb_tool = MCPTool(
        server_label="knowledge-base",
        server_url=mcp_endpoint,
        require_approval="never",
        allowed_tools=["knowledge_base_retrieve"],
        project_connection_id=kb_connection_name,
    )

    # MCPTool 2: GitHub リモート MCP サーバーへの接続（カタログツール形式）
    mcp_github_tool = MCPTool(
        server_label="GitHub",
        server_url="https://api.githubcopilot.com/mcp",
        require_approval="never",
        project_connection_id=GITHUB_CONNECTION_NAME,
    )

    agent = project_client.agents.create_version(
        agent_name=agent_name,
        definition=PromptAgentDefinition(
            model=model,
            instructions=instructions,
            tools=[mcp_kb_tool, mcp_github_tool],
        ),
    )

    logger.info(
        "✅ エージェント '%s' (version: %s) を作成しました",
        agent.name,
        agent.version,
    )


def main():
    parser = argparse.ArgumentParser(description="Foundry Agent Service セットアップ")
    parser.add_argument(
        "--skip-connection",
        action="store_true",
        help="プロジェクト接続の作成をスキップ",
    )
    parser.add_argument(
        "--skip-agent",
        action="store_true",
        help="エージェントの作成をスキップ",
    )
    args = parser.parse_args()

    cfg = get_config()

    if not args.skip_connection:
        logger.info("📡 プロジェクト接続を作成中...")
        create_project_connections(cfg)

    if not args.skip_agent:
        logger.info("🤖 エージェントを作成中...")
        create_agent(cfg)

    logger.info("🎉 セットアップ完了")


if __name__ == "__main__":
    main()
