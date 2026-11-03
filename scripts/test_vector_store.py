import sys
from pathlib import Path

# Add the project root to Python's import path.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.rag.vector_store import store_chunks, search_chunks, delete_document

TEST_DOCUMENT_ID = "vector_store_test"


def main():
    # Remove leftover test records before running the test.
    delete_document(TEST_DOCUMENT_ID)

    sample_chunks = [
        {
            "chunk_id": "page_4_chunk_1",
            "page_number": 4,
            "source_file": "sample_va_solicitation.pdf",
            "text": (
                "Proposal submission deadline: November 20, 2026, at 2:00 PM "
                "Eastern Time. The contractor must submit technical and price "
                "proposals electronically. Late submissions may be rejected. "
                "This is a fictional test passage."
            ),
        },
        {
            "chunk_id": "page_7_chunk_1",
            "page_number": 7,
            "source_file": "sample_va_solicitation.pdf",
            "text": (
                "The contractor should provide cloud infrastructure support, "
                "DevOps automation, CI/CD pipeline management, and technical "
                "documentation. This is a fictional test passage."
            ),
        },
    ]

    try:
        stored_count = store_chunks(
            chunks=sample_chunks,
            document_id=TEST_DOCUMENT_ID,
        )

        print(f"Passages stored: {stored_count}")

        if stored_count != 2:
            raise RuntimeError(
                f"Expected 2 stored passages, but got {stored_count}."
            )

        results = search_chunks(
            query="When is the proposal due?",
            document_id=TEST_DOCUMENT_ID,
            n_results=2,
        )

        print(f"Search results returned: {len(results)}")

        if not results:
            raise RuntimeError("The search returned no results.")

        for index, result in enumerate(results, start=1):
            print(f"\nResult {index}")
            print(f"Source file: {result['source_file']}")
            print(f"Page number: {result['page_number']}")
            print(f"Passage: {result['text']}")

        best_result = results[0]

        if best_result["page_number"] != 4:
            raise RuntimeError(
                "The top result was not the expected deadline passage "
                "on page 4."
            )

        if "November 20, 2026" not in best_result["text"]:
            raise RuntimeError(
                "The expected deadline was not found in the top result."
            )

        print("\nSUCCESS: ChromaDB stored and retrieved the correct passage.")
        print("SUCCESS: Source page metadata was preserved.")

    finally:
        removed_count = delete_document(TEST_DOCUMENT_ID)
        print(f"\nTemporary test passages removed: {removed_count}")


if __name__ == "__main__":
    main()
