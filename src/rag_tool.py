"""
RAG policy search tool.

Loads, chunks, and embeds the three policy/FAQ text files into a persistent
Chroma collection, then exposes a single `rag_policy_search` tool for the
agent. This tool is for POLICY questions only (returns window, shipping
timelines, refund timing, general FAQ) — never for a specific customer's
order/return/payment data, which must go through the SQL toolkit instead.
"""

from pathlib import Path
from typing import Optional

from langchain.tools import tool
from langchain_core.documents import Document
from langchain_openai import OpenAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

from src.config import CHROMA_DIR, OPENAI_API_KEY, POLICY_DIR, EMBEDDING_MODEL

try:
    from langchain_chroma import Chroma
except ImportError:  # fall back to the community package if langchain_chroma isn't installed
    from langchain_community.vectorstores import Chroma

_vector_store: Optional[Chroma] = None

COLLECTION_NAME = "policy_docs"


def _load_and_chunk_documents() -> list[Document]:
    splitter = RecursiveCharacterTextSplitter(chunk_size=800, chunk_overlap=120)
    docs: list[Document] = []
    for path in sorted(POLICY_DIR.glob("*.txt")):
        text = path.read_text(encoding="utf-8")
        for chunk in splitter.split_text(text):
            docs.append(Document(page_content=chunk, metadata={"source": path.name}))
    if not docs:
        raise FileNotFoundError(
            f"No policy .txt files found in {POLICY_DIR}. Expected returns_policy.txt, "
            "shipping_policy.txt, faq_returns_and_cancellations.txt."
        )
    return docs


def get_vector_store() -> Chroma:
    """Build (first run) or open (subsequent runs) the persisted Chroma
    collection, caching the instance for the process lifetime."""
    global _vector_store
    if _vector_store is not None:
        return _vector_store

    embeddings = OpenAIEmbeddings(model=EMBEDDING_MODEL, api_key=OPENAI_API_KEY)
    CHROMA_DIR.mkdir(parents=True, exist_ok=True)

    # If a collection already exists on disk with data, just open it.
    store = Chroma(
        collection_name=COLLECTION_NAME,
        embedding_function=embeddings,
        persist_directory=str(CHROMA_DIR),
    )
    if store._collection.count() == 0:
        docs = _load_and_chunk_documents()
        store = Chroma.from_documents(
            docs,
            embedding=embeddings,
            collection_name=COLLECTION_NAME,
            persist_directory=str(CHROMA_DIR),
        )

    _vector_store = store
    return _vector_store


@tool
def rag_policy_search(question: str) -> str:
    """Search the store's shipping/returns/cancellation POLICY and FAQ
    documents for an answer. Use this ONLY for general policy questions such
    as return windows, refund timelines, who pays for return shipping, or
    shipping delivery estimates.

    Do NOT use this tool for a specific customer's order status, return
    status, ticket status, or payment status — those require the SQL tools
    instead, since this index has no per-customer data.
    """
    store = get_vector_store()
    results = store.similarity_search(question, k=4)
    if not results:
        return "No relevant policy information was found for this question."

    formatted = []
    for i, doc in enumerate(results, start=1):
        source = doc.metadata.get("source", "policy")
        formatted.append(f"[{i}] (from {source})\n{doc.page_content}")
    return "\n\n".join(formatted)
