import chromadb

from app.config import get_settings

_settings = get_settings()
_client = chromadb.PersistentClient(path=_settings.chroma_persist_dir)
_collection = _client.get_or_create_collection(name="report_entries")


def upsert_entry(entry_id: int, text: str) -> None:
    _collection.upsert(
        ids=[str(entry_id)],
        documents=[text],
        metadatas=[{"entry_id": entry_id}],
    )


def query_similar(question: str, top_k: int = 5) -> list[dict]:
    results = _collection.query(query_texts=[question], n_results=top_k)

    documents = results.get("documents", [[]])[0]
    metadatas = results.get("metadatas", [[]])[0]

    return [
        {"entry_id": metadata["entry_id"], "text": document}
        for document, metadata in zip(documents, metadatas)
    ]
