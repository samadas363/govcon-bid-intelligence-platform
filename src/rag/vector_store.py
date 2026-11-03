import hashlib
from pathlib import Path
from typing import Any

import chromadb


PROJECT_ROOT = Path(__file__).resolve().parents[2]
VECTOR_DB_PATH = PROJECT_ROOT / "data" / "chroma_db"
COLLECTION_NAME = "govcon_solicitations"


def get_collection():
    """Create or open the persistent ChromaDB collection."""
    VECTOR_DB_PATH.mkdir(parents=True, exist_ok=True)

    client = chromadb.PersistentClient(path=str(VECTOR_DB_PATH))

    return client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"description": "Federal solicitation document passages"},
    )


def store_chunks(
    chunks: list[dict[str, Any]],
    document_id: str,
) -> int:
    """Store text chunks and their source-page metadata in ChromaDB."""
    if not document_id or not document_id.strip():
        raise ValueError("document_id must not be empty.")

    if not chunks:
        return 0

    collection = get_collection()
    ids = []
    documents = []
    metadatas = []

    for index, chunk in enumerate(chunks, start=1):
        text = str(chunk.get("text", "")).strip()

        if not text:
            continue

        page_number = int(chunk.get("page_number", 0))
        chunk_id = str(
            chunk.get("chunk_id", f"page_{page_number}_chunk_{index}")
        )

        stable_id = hashlib.sha256(
            f"{document_id}|{chunk_id}".encode("utf-8")
        ).hexdigest()

        ids.append(stable_id)
        documents.append(text)
        metadatas.append(
            {
                "document_id": document_id,
                "source_file": str(chunk.get("source_file", "unknown.pdf")),
                "page_number": page_number,
                "chunk_id": chunk_id,
            }
        )

    if not ids:
        return 0

    collection.upsert(
        ids=ids,
        documents=documents,
        metadatas=metadatas,
    )

    return len(ids)


def search_chunks(
    query: str,
    document_id: str | None = None,
    n_results: int = 5,
) -> list[dict[str, Any]]:
    """Find relevant passages and return their source-page references."""
    query = query.strip()

    if not query:
        raise ValueError("Search query must not be empty.")

    if n_results < 1:
        raise ValueError("n_results must be at least 1.")

    collection = get_collection()
    total = collection.count()

    if total == 0:
        return []

    query_args = {
        "query_texts": [query],
        "n_results": min(n_results, total),
    }

    if document_id:
        query_args["where"] = {"document_id": document_id}

    results = collection.query(**query_args)

    ids = results.get("ids", [[]])[0]
    documents = results.get("documents", [[]])[0]
    metadatas = results.get("metadatas", [[]])[0]
    distances = results.get("distances", [[]])[0]

    matches = []

    for index, text in enumerate(documents):
        metadata = metadatas[index] or {}

        matches.append(
            {
                "id": ids[index],
                "text": text,
                "document_id": metadata.get("document_id"),
                "source_file": metadata.get("source_file"),
                "page_number": metadata.get("page_number"),
                "chunk_id": metadata.get("chunk_id"),
                "distance": (
                    distances[index] if index < len(distances) else None
                ),
            }
        )

    return matches


def delete_document(document_id: str) -> int:
    """Delete indexed chunks for one specified document."""
    if not document_id or not document_id.strip():
        raise ValueError("document_id must not be empty.")

    collection = get_collection()

    existing = collection.get(
        where={"document_id": document_id},
        include=[],
    )

    ids = existing.get("ids", [])

    if ids:
        collection.delete(ids=ids)

    return len(ids)


if __name__ == "__main__":
    collection = get_collection()

    print("CHROMADB CONNECTION SUCCESSFUL")
    print(f"Collection: {COLLECTION_NAME}")
    print(f"Stored chunks: {collection.count()}")
    print(f"Database directory: {VECTOR_DB_PATH}")
