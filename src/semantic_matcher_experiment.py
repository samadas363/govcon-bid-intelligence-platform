"""
TTE Semantic Matching Experiment
=================================

Purpose:
    Compare the existing keyword-based qualification results with
    semantic similarity between real opportunities and TTE capabilities.

Safety:
    - Reads opportunities from PostgreSQL.
    - Does not modify database records.
    - Does not change the existing qualification engine.
    - Does not make eligibility or bid/no-bid decisions.
    - Writes a separate CSV research report.
"""

import csv
from pathlib import Path

import numpy as np
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity

from src.company_profile import get_company_profile
from src.qualification_engine import (
    load_opportunities_for_qualification,
    qualify_opportunity,
)


# ============================================================
# CONFIGURATION
# ============================================================

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"

PROJECT_ROOT = Path(__file__).resolve().parent.parent
REPORT_DIR = PROJECT_ROOT / "data" / "reports"

REPORT_FILE = REPORT_DIR / "semantic_match_experiment.csv"

MAX_TEXT_CHARACTERS = 5000
TOP_RESULTS_TO_DISPLAY = 15

PROFILE = get_company_profile()

TARGET_NAICS = {
    str(code).strip()
    for code in PROFILE.get("target_naics_codes", [])
    if code is not None
}


# ============================================================
# CAPABILITY DOCUMENTS
# ============================================================

def build_capability_documents():
    """
    Build individual semantic reference documents from TTE's
    existing company profile.

    Only profile information is used. No capabilities are invented.
    """

    documents = []

    for item in PROFILE.get("core_competencies", []):
        if item:
            documents.append({
                "category": "Core Competency",
                "text": str(item).strip(),
            })

    for item in PROFILE.get("project_experience", []):
        if item:
            documents.append({
                "category": "Project Experience",
                "text": str(item).strip(),
            })

    for group_name, keywords in PROFILE.get(
        "keyword_groups", {}
    ).items():

        if not keywords:
            continue

        phrase_list = ", ".join(
            str(keyword).strip()
            for keyword in keywords
            if keyword
        )

        if phrase_list:
            documents.append({
                "category": "Keyword Group",
                "text": f"{group_name.replace('_', ' ')}: {phrase_list}",
            })

    # Remove duplicate documents while preserving order.
    unique_documents = []
    seen = set()

    for document in documents:
        key = (
            document["category"].lower(),
            document["text"].lower(),
        )

        if key not in seen:
            seen.add(key)
            unique_documents.append(document)

    return unique_documents


# ============================================================
# TEXT HELPERS
# ============================================================

def clean_text(value):
    """Convert database values to clean strings."""

    if value is None:
        return ""

    return " ".join(str(value).split())


def get_opportunity_text(opportunity):
    """
    Build text from the same principal fields used by the
    existing qualification engine, plus agency information.
    """

    fields = [
        "title",
        "description",
        "opportunity_type",
        "solicitation_number",
        "agency_name",
    ]

    parts = []

    for field in fields:
        value = clean_text(opportunity.get(field))

        if value:
            parts.append(value)

    text = " ".join(parts)

    return text[:MAX_TEXT_CHARACTERS]


def normalize_naics(value):
    """Normalize NAICS codes for exact comparison."""

    if value is None:
        return ""

    return str(value).strip()


# ============================================================
# EXISTING ENGINE BASELINE
# ============================================================

def get_original_qualification(opportunity):
    """
    Run the existing qualification logic in memory.

    This does not write scores to PostgreSQL.
    """

    result = qualify_opportunity(opportunity)

    scores = result.get("scores", {})
    technical = scores.get("technical", {})
    naics = scores.get("naics", {})

    return {
        "original_overall_score": result.get("total_score", 0),
        "original_technical_score": technical.get("score", 0),
        "original_technical_maximum": technical.get("maximum", 40),
        "original_matched_groups": ", ".join(
            technical.get("matched_groups", [])
        ),
        "original_matched_keywords": ", ".join(
            technical.get("matched_keywords", [])
        ),
        "original_naics_match": bool(naics.get("match", False)),
    }


# ============================================================
# SEMANTIC MATCHING
# ============================================================

def calculate_semantic_matches(
    opportunity_text,
    model,
    capability_documents,
    capability_embeddings,
):
    """
    Calculate cosine similarity between an opportunity and
    individual TTE capability reference documents.

    Similarity is an exploratory ranking signal only.
    It is not a probability, qualification score, or proof
    of capability.
    """

    if not opportunity_text.strip():
        return {
            "semantic_similarity": None,
            "best_capability": "",
            "best_capability_category": "",
            "second_capability": "",
            "second_similarity": None,
            "third_capability": "",
            "third_similarity": None,
        }

    opportunity_embedding = model.encode(
        [opportunity_text],
        normalize_embeddings=True,
        show_progress_bar=False,
    )

    similarities = cosine_similarity(
        opportunity_embedding,
        capability_embeddings,
    )[0]

    ranked_indices = np.argsort(similarities)[::-1]

    best_index = int(ranked_indices[0])

    second_index = (
        int(ranked_indices[1])
        if len(ranked_indices) > 1
        else None
    )

    third_index = (
        int(ranked_indices[2])
        if len(ranked_indices) > 2
        else None
    )

    best_similarity = float(similarities[best_index])

    second_similarity = (
        float(similarities[second_index])
        if second_index is not None
        else None
    )

    third_similarity = (
        float(similarities[third_index])
        if third_index is not None
        else None
    )

    best_document = capability_documents[best_index]

    return {
        "semantic_similarity": round(best_similarity, 4),
        "best_capability": best_document["text"],
        "best_capability_category": best_document["category"],
        "second_capability": (
            capability_documents[second_index]["text"]
            if second_index is not None
            else ""
        ),
        "second_similarity": (
            round(second_similarity, 4)
            if second_similarity is not None
            else None
        ),
        "third_capability": (
            capability_documents[third_index]["text"]
            if third_index is not None
            else ""
        ),
        "third_similarity": (
            round(third_similarity, 4)
            if third_similarity is not None
            else None
        ),
    }


# ============================================================
# REPORTING
# ============================================================

def write_csv_report(results):
    """Write the experiment to a separate CSV file."""

    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    if not results:
        print("No results available for export.")
        return

    fieldnames = list(results[0].keys())

    with REPORT_FILE.open(
        "w",
        newline="",
        encoding="utf-8-sig",
    ) as csv_file:

        writer = csv.DictWriter(
            csv_file,
            fieldnames=fieldnames,
            extrasaction="ignore",
        )

        writer.writeheader()
        writer.writerows(results)

    print(f"\nCSV report saved to:\n{REPORT_FILE}")


def print_top_results(results):
    """Print the highest semantic similarity results."""

    ranked = sorted(
        results,
        key=lambda row: (
            row["semantic_similarity"]
            if row["semantic_similarity"] is not None
            else -1
        ),
        reverse=True,
    )

    print("\n" + "=" * 100)
    print("TOP OPPORTUNITIES BY SEMANTIC SIMILARITY")
    print("=" * 100)

    for index, row in enumerate(
        ranked[:TOP_RESULTS_TO_DISPLAY],
        start=1,
    ):
        similarity = row["semantic_similarity"]

        print(f"\nRank: {index}")
        print(f"ID: {row['opportunity_id']}")
        print(f"Title: {row['title']}")
        print(f"Agency: {row['agency_name']}")
        print(f"NAICS: {row['naics_code']}")
        print(f"Exact target NAICS match: {row['target_naics_match']}")
        print(f"Original technical score: "
              f"{row['original_technical_score']}/"
              f"{row['original_technical_maximum']}")

        print(
            "Semantic similarity (cosine): "
            f"{similarity if similarity is not None else 'Unavailable'}"
        )

        print(
            "Best matching TTE capability: "
            f"{row['best_capability'] or 'None'}"
        )

        print(
            "Capability evidence category: "
            f"{row['best_capability_category'] or 'None'}"
        )

        print(f"Opportunity type: {row['opportunity_type']}")

        print(
            "Review note: Semantic similarity is exploratory; "
            "verify the statement of work and eligibility."
        )

        print("-" * 100)


# ============================================================
# MAIN EXPERIMENT
# ============================================================

def main():
    print("=" * 100)
    print("TTE SEMANTIC MATCHING EXPERIMENT")
    print("=" * 100)

    print(f"Company: {PROFILE.get('company_name')}")
    print(f"Target NAICS codes: {len(TARGET_NAICS)}")
    print(f"Model: {MODEL_NAME}")
    print("Database writes: NONE")
    print("Existing engine modifications: NONE")

    # Build reference documents from the profile.
    capability_documents = build_capability_documents()

    if not capability_documents:
        raise RuntimeError(
            "No capability reference documents were found "
            "in the TTE profile."
        )

    print(
        f"\nCapability reference documents: "
        f"{len(capability_documents)}"
    )

    # Load the cached model.
    print("\nLoading the sentence-embedding model...")

    model = SentenceTransformer(MODEL_NAME)

    # Precompute reference embeddings once.
    print("Encoding TTE capability references...")

    capability_texts = [
        document["text"]
        for document in capability_documents
    ]

    capability_embeddings = model.encode(
        capability_texts,
        normalize_embeddings=True,
        show_progress_bar=False,
    )

    # Load only real opportunities.
    print("\nLoading real opportunity records...")

    opportunities = load_opportunities_for_qualification(
        include_samples=False
    )

    print(f"Real records loaded: {len(opportunities)}")

    results = []

    for index, opportunity in enumerate(
        opportunities,
        start=1,
    ):
        opportunity_id = opportunity.get("opportunity_id")

        title = clean_text(opportunity.get("title"))
        agency = clean_text(opportunity.get("agency_name"))
        opportunity_type = clean_text(
            opportunity.get("opportunity_type")
        )
        naics = normalize_naics(
            opportunity.get("naics_code")
        )

        text = get_opportunity_text(opportunity)

        original = get_original_qualification(opportunity)

        semantic = calculate_semantic_matches(
            text,
            model,
            capability_documents,
            capability_embeddings,
        )

        target_naics_match = naics in TARGET_NAICS

        row = {
            "opportunity_id": opportunity_id,
            "title": title,
            "agency_name": agency,
            "opportunity_type": opportunity_type,
            "naics_code": naics,
            "target_naics_match": target_naics_match,
            **original,
            **semantic,
            "review_note": (
                "Exploratory semantic result only; "
                "verify requirements, deadline, and eligibility."
            ),
        }

        results.append(row)

        if index % 10 == 0 or index == len(opportunities):
            print(
                f"Processed {index}/{len(opportunities)} "
                "opportunities..."
            )

    # Save separate research report.
    write_csv_report(results)

    # Display top semantic matches.
    print_top_results(results)

    # Final summary.
    naics_matches = sum(
        1 for row in results if row["target_naics_match"]
    )

    zero_keyword_matches = sum(
        1
        for row in results
        if row["original_technical_score"] == 0
    )

    print("\n" + "=" * 100)
    print("EXPERIMENT COMPLETED")
    print("=" * 100)
    print(f"Records evaluated: {len(results)}")
    print(f"Exact target NAICS matches: {naics_matches}")
    print(f"Records with zero original technical score: "
          f"{zero_keyword_matches}")
    print(f"CSV report: {REPORT_FILE}")
    print("\nNo database records were modified.")
    print("No production scoring logic was changed.")
    print(
        "Semantic similarity must not be interpreted as "
        "a bid-success probability or eligibility determination."
    )


if __name__ == "__main__":
    main()
