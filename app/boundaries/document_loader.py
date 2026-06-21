import os
from pathlib import Path

from llama_index.core import (
    Settings,
    SimpleDirectoryReader,
    StorageContext,
    VectorStoreIndex,
    load_index_from_storage,
)
from llama_index.core.node_parser import SentenceSplitter
from llama_index.embeddings.openai import OpenAIEmbedding

POLICIES_DIR = Path(__file__).parent.parent / "docs" / "policies"
STORAGE_DIR = Path(os.getenv("RAG_STORAGE_DIR", "./storage"))

_index: VectorStoreIndex | None = None


def build_index() -> None:
    """
    앱 시작 시 1회 호출.
    storage/ 폴더가 있으면 로드, 없으면 임베딩 후 저장.
    """
    global _index
    if os.getenv("HSA_TEST_MODE") == "true":
        return

    Settings.embed_model = OpenAIEmbedding(model="text-embedding-3-small")
    Settings.llm = None  # LlamaIndex 내부 LLM 사용 안 함 — Pydantic AI만 사용

    if STORAGE_DIR.exists() and any(STORAGE_DIR.iterdir()):
        storage_context = StorageContext.from_defaults(persist_dir=str(STORAGE_DIR))
        _index = load_index_from_storage(storage_context)
    else:
        docs = SimpleDirectoryReader(str(POLICIES_DIR)).load_data()
        splitter = SentenceSplitter(chunk_size=512, chunk_overlap=50)
        _index = VectorStoreIndex.from_documents(docs, transformations=[splitter])
        STORAGE_DIR.mkdir(parents=True, exist_ok=True)
        _index.storage_context.persist(persist_dir=str(STORAGE_DIR))


def get_index() -> VectorStoreIndex:
    if _index is None:
        raise RuntimeError("Document index not initialized. Call build_index() first.")
    return _index
