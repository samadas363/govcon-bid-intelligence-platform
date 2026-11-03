from pathlib import Path
from typing import Any
import argparse

import pymupdf


def extract_pdf_pages(pdf_path: str | Path) -> list[dict[str, Any]]:
    """Extract text from each PDF page and retain page numbers."""
    path = Path(pdf_path)

    if not path.exists():
        raise FileNotFoundError(f"PDF file not found: {path}")

    if path.suffix.lower() != ".pdf":
        raise ValueError("The supplied file must have a .pdf extension.")

    pages = []

    try:
        with pymupdf.open(str(path)) as document:

            if document.needs_pass:
                if not document.authenticate(""):
                    raise ValueError(
                        "This PDF is encrypted. Provide an accessible, "
                        "unencrypted PDF."
                    )

            for page_number, page in enumerate(document, start=1):
                text = (page.get_text("text") or "").strip()

                pages.append(
                    {
                        "page_number": page_number,
                        "text": text,
                        "has_text": bool(text),
                    }
                )

    except ValueError:
        raise
    except Exception as exc:
        raise ValueError(f"Could not read PDF: {exc}") from exc

    if not pages:
        raise ValueError("The PDF contains no pages.")

    return pages


def chunk_text(
    text: str,
    chunk_size: int = 1200,
    overlap: int = 200,
) -> list[str]:
    """Split text into overlapping character-based chunks."""
    if chunk_size <= 0:
        raise ValueError("chunk_size must be greater than zero.")

    if overlap < 0 or overlap >= chunk_size:
        raise ValueError(
            "overlap must be at least 0 and smaller than chunk_size."
        )

    text = " ".join(text.split())

    if not text:
        return []

    chunks = []
    start = 0

    while start < len(text):
        end = min(start + chunk_size, len(text))
        chunk = text[start:end].strip()

        if chunk:
            chunks.append(chunk)

        if end == len(text):
            break

        start = end - overlap

    return chunks


def process_pdf(
    pdf_path: str | Path,
    chunk_size: int = 1200,
    overlap: int = 200,
) -> dict[str, Any]:
    """Extract PDF text and create chunks with source-page metadata."""
    pages = extract_pdf_pages(pdf_path)

    chunks = []
    empty_pages = []

    for page in pages:
        page_number = page["page_number"]
        text = page["text"]

        if not text:
            empty_pages.append(page_number)
            continue

        page_chunks = chunk_text(
            text,
            chunk_size=chunk_size,
            overlap=overlap,
        )

        for chunk_index, chunk in enumerate(page_chunks, start=1):
            chunks.append(
                {
                    "chunk_id": f"page_{page_number}_chunk_{chunk_index}",
                    "page_number": page_number,
                    "chunk_index": chunk_index,
                    "text": chunk,
                    "source_file": Path(pdf_path).name,
                }
            )

    return {
        "source_file": Path(pdf_path).name,
        "page_count": len(pages),
        "pages_with_text": sum(1 for page in pages if page["has_text"]),
        "empty_pages": empty_pages,
        "chunks": chunks,
        "chunk_count": len(chunks),
    }


def main():
    parser = argparse.ArgumentParser(
        description="Extract text and create source-referenced chunks from a PDF."
    )
    parser.add_argument("pdf_path", help="Path to the solicitation PDF.")
    parser.add_argument("--chunk-size", type=int, default=1200)
    parser.add_argument("--overlap", type=int, default=200)

    args = parser.parse_args()

    try:
        result = process_pdf(
            args.pdf_path,
            chunk_size=args.chunk_size,
            overlap=args.overlap,
        )

        print("\nPDF PROCESSING COMPLETE")
        print("-" * 45)
        print(f"File: {result['source_file']}")
        print(f"Pages: {result['page_count']}")
        print(f"Pages with extractable text: {result['pages_with_text']}")
        print(f"Chunks created: {result['chunk_count']}")

        if result["empty_pages"]:
            print(f"Pages with no extractable text: {result['empty_pages']}")
            print("These pages may require OCR if they contain scanned images.")

        if result["chunks"]:
            print("\nFirst chunk preview:")
            print(result["chunks"][0]["text"][:500])

        print("\nNo database records were changed.")

    except Exception as exc:
        print(f"\nPDF PROCESSING FAILED: {exc}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
