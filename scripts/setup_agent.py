"""Foundry Agent Service エージェントセットアップ.

RemoteTool プロジェクト接続と Prompt Agent を作成する。
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


def get_config():
    """環境変数から設定を取得する."""
    required = {
        "PROJECT_ENDPOINT": os.getenv("PROJECT_ENDPOINT", ""),
        "AZURE_SEARCH_ENDPOINT": os.getenv("AZURE_SEARCH_ENDPOINT", ""),
        "FOUNDRY_IQ_KNOWLEDGE_BASE_NAME": os.getenv("FOUNDRY_IQ_KNOWLEDGE_BASE_NAME", "system-inquiry-kb"),
        "PROJECT_CONNECTION_NAME": os.getenv("PROJECT_CONNECTION_NAME", "kb-mcp-connection"),
        "AGENT_NAME": os.getenv("AGENT_NAME", "system-inquiry-agent"),
        "AZURE_OPENAI_CHAT_DEPLOYMENT": os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT", "gpt-4o"),
    }
    missing = [k for k, v in required.items() if not v]
    if missing:
        logger.error("環境変数が未設定: %s", ", ".join(missing))
        sys.exit(1)
    return required


def create_project_connection(cfg: dict) -> None:
    """RemoteTool プロジェクト接続を作成する（KB MCP エンドポイント）."""
    credential = DefaultAzureCredential()

    search_endpoint = cfg["AZURE_SEARCH_ENDPOINT"]
    kb_name = cfg["FOUNDRY_IQ_KNOWLEDGE_BASE_NAME"]
    connection_name = cfg["PROJECT_CONNECTION_NAME"]

    mcp_endpoint = (
        f"{search_endpoint}/knowledgebases/{kb_name}/mcp"
        f"?api-version=2025-11-01-preview"
    )

    # Project の ARM リソース ID を取得
    # PROJECT_ENDPOINT 例: https://xxx.services.ai.azure.com/api/projects/yyy
    # ARM ID は別途取得が必要 — 環境変数で渡すか Azure CLI で取得
    project_resource_id = os.getenv("PROJECT_RESOURCE_ID", "")
    if not project_resource_id:
        logger.warning(
            "PROJECT_RESOURCE_ID が未設定です。\n"
            "Azure Portal → AI Project → プロパティ → リソース ID を確認してください。\n"
            "  export PROJECT_RESOURCE_ID=/subscriptions/.../resourceGroups/.../providers/...\n"
            "接続の作成をスキップします。"
        )
        return

    bearer_token_provider = get_bearer_token_provider(
        credential, "https://management.azure.com/.default"
    )

    response = requests.put(
        f"https://management.azure.com{project_resource_id}"
        f"/connections/{connection_name}?api-version=2025-10-01-preview",
        headers={"Authorization": f"Bearer {bearer_token_provider()}"},
        json={
            "name": connection_name,
            "type": "Microsoft.MachineLearningServices/workspaces/connections",
            "properties": {
                "authType": "ProjectManagedIdentity",
                "category": "RemoteTool",
                "target": mcp_endpoint,
                "isSharedToAll": True,
                "audience": "https://search.azure.com/",
                "metadata": {"ApiType": "Azure"},
            },
        },
        timeout=60,
    )
    response.raise_for_status()
    logger.info("✅ プロジェクト接続 '%s' を作成しました", connection_name)


def create_agent(cfg: dict) -> None:
    """Prompt Agent を作成する（MCPTool + GitHub Function Tools）."""
    credential = DefaultAzureCredential()
    project_client = AIProjectClient(
        endpoint=cfg["PROJECT_ENDPOINT"],
        credential=credential,
    )

    search_endpoint = cfg["AZURE_SEARCH_ENDPOINT"]
    kb_name = cfg["FOUNDRY_IQ_KNOWLEDGE_BASE_NAME"]
    connection_name = cfg["PROJECT_CONNECTION_NAME"]
    agent_name = cfg["AGENT_NAME"]
    model = cfg["AZURE_OPENAI_CHAT_DEPLOYMENT"]

    mcp_endpoint = (
        f"{search_endpoint}/knowledgebases/{kb_name}/mcp"
        f"?api-version=2025-11-01-preview"
    )

    instructions = """\
あなたは社内 IT システムの問い合わせ対応エージェントです。
以下の情報ソースを活用してユーザーの質問に回答します。

1. **インシデント情報**（Foundry IQ ナレッジベース）
   - ServiceNow に登録された過去のインシデント（障害、不具合、問い合わせ）
   - knowledge_base_retrieve ツール（MCP）で自動検索

2. **ソースコード・設計書**（GitHub リポジトリ）
   - search_code, get_file_content, list_repository_files ツールで取得

## 回答方針
- 質問の内容に応じて適切なツールを選択・組み合わせてください
- ナレッジベースからの情報には引用（annotation）を付与してください
- コードや設計書の該当箇所はファイルパスと内容を引用してください
- 不確かな情報は「確認中」と明記し、推測は推測と表記してください
- 回答は日本語で、構造化された形式で返してください
- ナレッジベースに回答がない場合は「該当する情報が見つかりませんでした」と回答してください
"""

    # MCPTool: Foundry IQ KB への接続
    mcp_kb_tool = MCPTool(
        server_label="knowledge-base",
        server_url=mcp_endpoint,
        require_approval="never",
        allowed_tools=["knowledge_base_retrieve"],
        project_connection_id=connection_name,
    )

    agent = project_client.agents.create_version(
        agent_name=agent_name,
        definition=PromptAgentDefinition(
            model=model,
            instructions=instructions,
            tools=[mcp_kb_tool],
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
        create_project_connection(cfg)

    if not args.skip_agent:
        logger.info("🤖 エージェントを作成中...")
        create_agent(cfg)

    logger.info("🎉 セットアップ完了")


if __name__ == "__main__":
    main()
