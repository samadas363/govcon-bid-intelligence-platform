import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.rag.pdf_processor import process_pdf
from src.rag.vector_store import store_chunks, search_chunks, delete_document


SOLICITATIONS_DIR = PROJECT_ROOT / "data" / "solicitations"


def ingest_pdf(pdf_path: Path) -> dict:
    """Extract a PDF's text and store its chunks in ChromaDB."""
    pdf_path = pdf_path.resolve()

    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    if pdf_path.suffix.lower() != ".pdf":
        raise ValueError("Only PDF files are supported.")

    print(f"\nProcessing PDF: {pdf_path.name}")

    result = process_pdf(pdf_path)

    print(f"Pages detected: {result['page_count']}")
    print(f"Pages containing text: {result['pages_with_text']}")
    print(f"Chunks extracted: {result['chunk_count']}")

    if result["empty_pages"]:
        print(f"Pages without extractable text: {result['empty_pages']}")
        print("These pages may need OCR if they contain scanned images.")

    if not result["chunks"]:
        raise ValueError(
            "No extractable text was found. Check whether the PDF is scanned."
        )

    # Use the filename as a simple document identifier for this initial version.
    document_id = pdf_path.name

    stored_count = store_chunks(
        chunks=result["chunks"],
        document_id=document_id,
    )

    print(f"Chunks stored or updated in ChromaDB: {stored_count}")

    return {
        "document_id": document_id,
        "source_file": pdf_path.name,
        "page_count": result["page_count"],
        "chunk_count": result["chunk_count"],
        "stored_count": stored_count,
    }


def main():
    if len(sys.argv) > 1:
        pdf_path = Path(sys.argv[1])

        if not pdf_path.is_absolute():
            pdf_path = PROJECT_ROOT / pdf_path
    else:
        pdf_files = sorted(SOLICITATIONS_DIR.glob("*.pdf"))

        if not pdf_files:
            print(f"No PDFs found in: {SOLICITATIONS_DIR}")
            print("Place a solicitation PDF in that folder and try again.")
            raise SystemExit(1)

        pdf_path = pdf_files[0]

    try:
        result = ingest_pdf(pdf_path)

        print("\n" + "=" * 50)
        print("SOLICITATION INGESTION COMPLETE")
        print("=" * 50)
        print(f"Document: {result['source_file']}")
        print(f"Document ID: {result['document_id']}")
        print(f"Pages: {result['page_count']}")
        print(f"Chunks extracted: {result['chunk_count']}")
        print(f"Chunks stored: {result['stored_count']}")
        print("\nNo PostgreSQL records were changed.")

    except Exception as exc:
        print(f"\nINGESTION FAILED: {exc}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
