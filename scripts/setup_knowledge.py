"""Foundry IQ ナレッジベース自動セットアップスクリプト.

Bicep デプロイ後に実行し、以下を自動化する:
  1. モック CSV を Blob Storage にアップロード
  2. Blob Knowledge Source を作成（自動でインデックス/インデクサー/スキルセット生成）
  3. Knowledge Base を作成
  4. インジェスト完了を待機

使い方:
  python -m scripts.setup_knowledge [--wait]
"""

from __future__ import annotations

import argparse
import os
import sys
import time

from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# 設定読み込み
# ---------------------------------------------------------------------------
SEARCH_ENDPOINT = os.environ.get("AZURE_SEARCH_ENDPOINT", "")
SEARCH_API_KEY = os.environ.get("AZURE_SEARCH_API_KEY", "")

OPENAI_ENDPOINT = os.environ.get("AZURE_OPENAI_ENDPOINT", "")
OPENAI_API_KEY = os.environ.get("AZURE_OPENAI_API_KEY", "")
OPENAI_CHAT_DEPLOYMENT = os.environ.get("AZURE_OPENAI_CHAT_DEPLOYMENT", "gpt-4o")
OPENAI_CHAT_MODEL = os.environ.get("AZURE_OPENAI_CHAT_MODEL_NAME", "gpt-4o")
OPENAI_EMBEDDING_DEPLOYMENT = os.environ.get(
    "AZURE_OPENAI_EMBEDDING_DEPLOYMENT", "text-embedding-3-large"
)
OPENAI_EMBEDDING_MODEL = os.environ.get(
    "AZURE_OPENAI_EMBEDDING_MODEL_NAME", "text-embedding-3-large"
)

BLOB_CONNECTION_STRING = os.environ.get("BLOB_CONNECTION_STRING", "")
BLOB_CONTAINER_NAME = os.environ.get("BLOB_CONTAINER_NAME", "incidents")

KNOWLEDGE_SOURCE_NAME = os.environ.get(
    "FOUNDRY_IQ_KNOWLEDGE_SOURCE_NAME", "incidents-blob-ks"
)
KNOWLEDGE_BASE_NAME = os.environ.get(
    "FOUNDRY_IQ_KNOWLEDGE_BASE_NAME", "system-inquiry-kb"
)

CSV_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "mock_incidents.csv")


def _validate_env() -> None:
    """必須環境変数の存在チェック."""
    required = {
        "AZURE_SEARCH_ENDPOINT": SEARCH_ENDPOINT,
        "AZURE_SEARCH_API_KEY": SEARCH_API_KEY,
        "AZURE_OPENAI_ENDPOINT": OPENAI_ENDPOINT,
        "BLOB_CONNECTION_STRING": BLOB_CONNECTION_STRING,
    }
    missing = [k for k, v in required.items() if not v]
    if missing:
        print(f"❌ 必須環境変数が未設定: {', '.join(missing)}")
        print("   .env ファイルを確認してください。")
        sys.exit(1)


# ---------------------------------------------------------------------------
# Step 1: Blob にデータアップロード
# ---------------------------------------------------------------------------
def upload_csv_to_blob(csv_path: str) -> None:
    """モック CSV を Blob コンテナにアップロードする."""
    from azure.identity import DefaultAzureCredential
    from azure.storage.blob import BlobServiceClient

    print(f"📤 CSV アップロード: {os.path.basename(csv_path)} → {BLOB_CONTAINER_NAME}")

    # キーベース認証が無効な場合は DefaultAzureCredential を使用
    storage_account_name = os.environ.get("BLOB_STORAGE_ACCOUNT_NAME", "")
    if storage_account_name:
        account_url = f"https://{storage_account_name}.blob.core.windows.net"
        credential = DefaultAzureCredential()
        blob_service = BlobServiceClient(account_url, credential=credential)
    else:
        blob_service = BlobServiceClient.from_connection_string(BLOB_CONNECTION_STRING)
    container_client = blob_service.get_container_client(BLOB_CONTAINER_NAME)

    # コンテナが存在しなければ作成
    try:
        container_client.get_container_properties()
    except Exception:
        container_client.create_container()
        print(f"   コンテナ '{BLOB_CONTAINER_NAME}' を作成しました")

    blob_name = os.path.basename(csv_path)
    blob_client = container_client.get_blob_client(blob_name)

    with open(csv_path, "rb") as f:
        blob_client.upload_blob(f, overwrite=True)

    print(f"   ✅ アップロード完了: {blob_name}")


# ---------------------------------------------------------------------------
# Step 2: Blob Knowledge Source 作成
# ---------------------------------------------------------------------------
def create_knowledge_source() -> None:
    """Blob Knowledge Source を作成する.

    自動的に data source, skillset, index, indexer が生成される。
    """
    from azure.core.credentials import AzureKeyCredential
    from azure.search.documents.indexes import SearchIndexClient
    from azure.search.documents.indexes.models import (
        AzureBlobKnowledgeSource,
        AzureBlobKnowledgeSourceParameters,
        AzureOpenAIVectorizerParameters,
        KnowledgeBaseAzureOpenAIModel,
        KnowledgeSourceAzureOpenAIVectorizer,
        KnowledgeSourceIngestionParameters,
    )

    print(f"🔧 Knowledge Source 作成: {KNOWLEDGE_SOURCE_NAME}")

    index_client = SearchIndexClient(
        endpoint=SEARCH_ENDPOINT,
        credential=AzureKeyCredential(SEARCH_API_KEY),
    )

    # Embedding モデルパラメータ
    embedding_params = AzureOpenAIVectorizerParameters(
        resource_url=OPENAI_ENDPOINT,
        deployment_name=OPENAI_EMBEDDING_DEPLOYMENT,
        model_name=OPENAI_EMBEDDING_MODEL,
        api_key=OPENAI_API_KEY if OPENAI_API_KEY else None,
    )

    # Chat Completion モデルパラメータ（画像言語化用、オプション）
    chat_params = AzureOpenAIVectorizerParameters(
        resource_url=OPENAI_ENDPOINT,
        deployment_name=OPENAI_CHAT_DEPLOYMENT,
        model_name=OPENAI_CHAT_MODEL,
        api_key=OPENAI_API_KEY if OPENAI_API_KEY else None,
    )

    knowledge_source = AzureBlobKnowledgeSource(
        name=KNOWLEDGE_SOURCE_NAME,
        description="ServiceNow インシデントデータ（モック CSV）",
        azure_blob_parameters=AzureBlobKnowledgeSourceParameters(
            connection_string=os.environ.get(
                "BLOB_RESOURCE_ID_CONNECTION_STRING",
                BLOB_CONNECTION_STRING,
            ),
            container_name=BLOB_CONTAINER_NAME,
            is_adls_gen2=False,
            ingestion_parameters=KnowledgeSourceIngestionParameters(
                disable_image_verbalization=True,
                embedding_model=KnowledgeSourceAzureOpenAIVectorizer(
                    azure_open_ai_parameters=embedding_params,
                ),
            ),
        ),
    )

    index_client.create_or_update_knowledge_source(knowledge_source)
    print(f"   ✅ Knowledge Source 作成完了: {KNOWLEDGE_SOURCE_NAME}")


# ---------------------------------------------------------------------------
# Step 3: Knowledge Base 作成
# ---------------------------------------------------------------------------
def create_knowledge_base() -> None:
    """Knowledge Base を作成し、Knowledge Source を紐付ける."""
    from azure.core.credentials import AzureKeyCredential
    from azure.search.documents.indexes import SearchIndexClient
    from azure.search.documents.indexes.models import (
        AzureOpenAIVectorizerParameters,
        KnowledgeBase,
        KnowledgeBaseAzureOpenAIModel,
        KnowledgeRetrievalLowReasoningEffort,
        KnowledgeRetrievalOutputMode,
        KnowledgeSourceReference,
    )

    print(f"🔧 Knowledge Base 作成: {KNOWLEDGE_BASE_NAME}")

    index_client = SearchIndexClient(
        endpoint=SEARCH_ENDPOINT,
        credential=AzureKeyCredential(SEARCH_API_KEY),
    )

    # LLM モデル接続
    llm_params = AzureOpenAIVectorizerParameters(
        resource_url=OPENAI_ENDPOINT,
        deployment_name=OPENAI_CHAT_DEPLOYMENT,
        model_name=OPENAI_CHAT_MODEL,
        api_key=OPENAI_API_KEY if OPENAI_API_KEY else None,
    )

    knowledge_base = KnowledgeBase(
        name=KNOWLEDGE_BASE_NAME,
        description="社内 IT システム問い合わせ対応用ナレッジベース。インシデント情報を検索・回答合成する。",
        knowledge_sources=[
            KnowledgeSourceReference(name=KNOWLEDGE_SOURCE_NAME),
        ],
        models=[
            KnowledgeBaseAzureOpenAIModel(azure_open_ai_parameters=llm_params),
        ],
        retrieval_reasoning_effort=KnowledgeRetrievalLowReasoningEffort(),
        output_mode=KnowledgeRetrievalOutputMode.ANSWER_SYNTHESIS,
        retrieval_instructions=(
            "インシデント番号、カテゴリ、優先度、説明、解決策を含めて回答してください。"
            "日本語で回答し、関連するインシデントを引用してください。"
        ),
    )

    index_client.create_or_update_knowledge_base(knowledge_base)
    print(f"   ✅ Knowledge Base 作成完了: {KNOWLEDGE_BASE_NAME}")


# ---------------------------------------------------------------------------
# Step 4: インジェスト状態チェック
# ---------------------------------------------------------------------------
def wait_for_ingestion(timeout_sec: int = 300) -> None:
    """Knowledge Source のインジェスト完了を待機する."""
    from azure.core.credentials import AzureKeyCredential
    from azure.search.documents.indexes import SearchIndexClient

    print(f"⏳ インジェスト待機中... (最大 {timeout_sec} 秒)")

    index_client = SearchIndexClient(
        endpoint=SEARCH_ENDPOINT,
        credential=AzureKeyCredential(SEARCH_API_KEY),
    )

    start = time.time()
    while (time.time() - start) < timeout_sec:
        try:
            status = index_client.get_knowledge_source_status(KNOWLEDGE_SOURCE_NAME)
            sync_status = getattr(status, "synchronization_status", "unknown")
            current = getattr(status, "current_synchronization_state", None)
            processed = getattr(current, "item_updates_processed", 0) if current else 0
            failed = getattr(current, "items_updates_failed", 0) if current else 0

            print(
                f"   状態: {sync_status} | 処理済み: {processed} | 失敗: {failed} "
                f"[{int(time.time() - start)}s]"
            )

            if sync_status not in ("creating", "active"):
                print(f"   ✅ インジェスト完了 (状態: {sync_status})")
                return
        except Exception as e:
            print(f"   ⚠️ ステータス取得エラー: {e}")

        time.sleep(15)

    print(f"   ⚠️ タイムアウト ({timeout_sec}s)。バックグラウンドで処理が継続中の場合があります。")


# ---------------------------------------------------------------------------
# メイン
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(
        description="Foundry IQ ナレッジベース自動セットアップ"
    )
    parser.add_argument(
        "--csv",
        default=CSV_PATH,
        help="アップロードする CSV ファイルパス",
    )
    parser.add_argument(
        "--wait",
        action="store_true",
        help="インジェスト完了まで待機する",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=300,
        help="インジェスト待機タイムアウト (秒)",
    )
    parser.add_argument(
        "--skip-upload",
        action="store_true",
        help="Blob アップロードをスキップ",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("🚀 Foundry IQ ナレッジベース セットアップ")
    print("=" * 60)

    _validate_env()

    # Step 1: Blob アップロード
    if not args.skip_upload:
        csv_path = os.path.abspath(args.csv)
        if not os.path.exists(csv_path):
            print(f"❌ CSV ファイルが見つかりません: {csv_path}")
            sys.exit(1)
        upload_csv_to_blob(csv_path)
    else:
        print("⏭️  Blob アップロードをスキップ")

    # Step 2: Knowledge Source 作成
    create_knowledge_source()

    # Step 3: Knowledge Base 作成
    create_knowledge_base()

    # Step 4: インジェスト待機（オプション）
    if args.wait:
        wait_for_ingestion(timeout_sec=args.timeout)

    print()
    print("=" * 60)
    print("✅ セットアップ完了！")
    print(f"   Knowledge Source: {KNOWLEDGE_SOURCE_NAME}")
    print(f"   Knowledge Base:   {KNOWLEDGE_BASE_NAME}")
    print(f"   Search Endpoint:  {SEARCH_ENDPOINT}")
    print()
    print("次のステップ:")
    print("  1. Azure Portal で indexer のステータスを確認")
    print("  2. streamlit run src/app.py でチャット UI を起動")
    print("=" * 60)


if __name__ == "__main__":
    main()
