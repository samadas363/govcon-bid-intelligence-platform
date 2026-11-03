import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.rag.claude_assistant import ask_solicitation


REPORTS_DIR = PROJECT_ROOT / "data" / "reports"

ANALYSIS_PROMPT = """
Analyze the supplied federal solicitation document excerpts.

Return ONLY valid JSON. Do not use Markdown fences or introductory text.

Use this exact JSON structure:

{
  "document_overview": {
    "title": "",
    "agency": "",
    "solicitation_number": "",
    "notice_type": "",
    "summary": ""
  },
  "scope_of_work": {
    "status": "found or not_found",
    "findings": []
  },
  "technical_requirements": {
    "status": "found or not_found",
    "findings": []
  },
  "mandatory_requirements": {
    "status": "found or not_found",
    "findings": []
  },
  "deliverables": {
    "status": "found or not_found",
    "findings": []
  },
  "submission_instructions": {
    "status": "found or not_found",
    "findings": []
  },
  "deadlines": {
    "status": "found or not_found",
    "findings": []
  },
  "evaluation_criteria": {
    "status": "found or not_found",
    "findings": []
  },
  "potential_risks": {
    "status": "identified, none_identified, or insufficient_information",
    "findings": []
  },
  "missing_information": [],
  "overall_assessment": ""
}

RULES:

1. Use only the supplied solicitation excerpts.
2. Never invent information.
3. For every finding, include a source citation in this format:
   {"item": "Finding", "evidence": "Supporting document wording",
    "source": "filename, page number"}
4. If information is unavailable, use an empty string or empty list
   and mark the relevant status as not_found.
5. Preserve exact dates, times, time zones and amounts.
6. Separate mandatory requirements from recommendations.
7. Identify unclear, conflicting or potentially restrictive requirements.
8. Do not assume that a document is a real government solicitation.
9. If the document identifies itself as fictional or a sample,
   clearly state that in the overall assessment.
10. Return valid JSON only. No comments or trailing commas.
"""


def extract_json(text):
    """Extract a JSON object from Claude's response."""
    text = text.strip()

    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    start = text.find("{")
    end = text.rfind("}")

    if start >= 0 and end > start:
        return json.loads(text[start:end + 1])

    raise ValueError("Claude did not return a valid JSON object.")


def analyze_document(document_id, n_results=10):
    print("=" * 65)
    print("GOVCON STRUCTURED SOLICITATION ANALYZER")
    print("=" * 65)
    print(f"Document: {document_id}")
    print("Retrieving indexed solicitation passages...")

    result = ask_solicitation(
        question=ANALYSIS_PROMPT,
        document_id=document_id,
        n_results=n_results,
    )

    passages = result.get("retrieved_passages", [])

    if not passages:
        raise RuntimeError(
            "No indexed passages found. Ingest the PDF before analysis."
        )

    print(f"Retrieved passages: {len(passages)}")
    print(f"Claude model: {result.get('model')}")
    print("Generating structured analysis...")

    answer = result["answer"]

    try:
        analysis = extract_json(answer)
        parse_status = "structured"
    except (ValueError, json.JSONDecodeError):
        analysis = {
            "analysis_text": answer,
            "warning": (
                "Claude returned text that could not be parsed as JSON. "
                "Review the analysis manually."
            ),
        }
        parse_status = "unstructured_fallback"

    report = {
        "report_generated_at": datetime.now(timezone.utc).isoformat(),
        "document_id": document_id,
        "analysis_status": parse_status,
        "model": result.get("model"),
        "retrieved_passage_count": len(passages),
        "sources": result.get("sources", []),
        "analysis": analysis,
        "api_usage": result.get("usage", {}),
    }

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    document_name = Path(document_id).stem
    report_path = REPORTS_DIR / (
        f"{document_name}_analysis_{timestamp}.json"
    )

    with report_path.open("w", encoding="utf-8") as file:
        json.dump(report, file, indent=4, ensure_ascii=False)

    print("\n" + "=" * 65)
    print("SOLICITATION ANALYSIS COMPLETE")
    print("=" * 65)
    print(f"Document: {document_id}")
    print(f"Retrieved passages: {len(passages)}")
    print(f"Analysis format: {parse_status}")
    print(f"Report saved: {report_path}")

    if result.get("usage"):
        print(f"Input tokens: {result['usage'].get('input_tokens')}")
        print(f"Output tokens: {result['usage'].get('output_tokens')}")

    if parse_status != "structured":
        print("\nWARNING: Review the unstructured analysis in the JSON report.")

    print("\nPostgreSQL was not accessed or modified.")

    return report_path


def main():
    parser = argparse.ArgumentParser(
        description="Generate a structured solicitation analysis JSON report."
    )

    parser.add_argument(
        "document_id",
        nargs="?",
        default="sample_it_solicitation.pdf",
        help="Indexed ChromaDB document ID.",
    )

    parser.add_argument(
        "--results",
        type=int,
        default=10,
        help="Maximum number of passages to retrieve (1-10).",
    )

    args = parser.parse_args()

    if not 1 <= args.results <= 10:
        parser.error("--results must be between 1 and 10.")

    try:
        analyze_document(
            document_id=args.document_id,
            n_results=args.results,
        )
    except Exception as exc:
        print(f"\nANALYSIS FAILED: {type(exc).__name__}: {exc}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
