import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.rag.vector_store import search_chunks, get_collection

DOCUMENT_ID = "sample_it_solicitation.pdf"

QUESTIONS = [
    "What is the deadline for submitting the proposal?",
    "What technical services and requirements are included?",
    "What are the proposal submission instructions?",
]

def main():
    collection = get_collection()

    print("=" * 65)
    print("GOVCON SOLICITATION RETRIEVAL TEST")
    print("=" * 65)
    print(f"ChromaDB collection: {collection.name}")
    print(f"Total indexed chunks: {collection.count()}")
    print(f"Target document: {DOCUMENT_ID}")

    indexed = collection.get(
        where={"document_id": DOCUMENT_ID},
        include=["metadatas"],
    )

    document_chunks = len(indexed.get("ids", []))
    print(f"Chunks indexed for this document: {document_chunks}")

    if document_chunks == 0:
        print("\nERROR: No chunks found for this PDF.")
        print("Run: python scripts\\ingest_solicitation.py")
        return

    for question in QUESTIONS:
        print("\n" + "-" * 65)
        print(f"QUESTION: {question}")
        print("-" * 65)

        results = search_chunks(
            query=question,
            document_id=DOCUMENT_ID,
            n_results=3,
        )

        if not results:
            print("No matching passages found.")
            continue

        for number, result in enumerate(results, start=1):
            print(f"\nResult {number}")
            print(f"Source: {result['source_file']}")
            print(f"Page: {result['page_number']}")
            print(f"Distance: {result['distance']}")
            print(f"Passage:\n{result['text']}")

    print("\n" + "=" * 65)
    print("RETRIEVAL TEST COMPLETE")
    print("=" * 65)
    print("No database records were changed.")

if __name__ == "__main__":
    main()
