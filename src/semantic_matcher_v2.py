from __future__ import annotations

import csv
import re
from pathlib import Path

import numpy as np
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity

from src.company_profile import get_company_profile
from src.qualification_engine import load_opportunities_for_qualification


MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
OUTPUT_FILE = Path("data/reports/semantic_match_v2.csv")

# These are review thresholds, not probabilities of winning a contract.
SEMANTIC_REVIEW_THRESHOLD = 0.35
SEMANTIC_STRONG_THRESHOLD = 0.45

PRODUCT_TITLE_PATTERN = re.compile(
    r"^\s*\d{2}\s*--|"
    r"\b("
    r"disk assembly|pump|parts kit|light|flange|panel|compressor|"
    r"reducer|block tackle|armor|coil|drain|switch|plate|"
    r"filter element|washer.?dryer|bearing|bolt|cable assembly|"
    r"hose|motor|battery|valve|cartridge"
    r")\b",
    re.IGNORECASE,
)

GENERIC_TERMS = {
    "support",
    "services",
    "service",
    "management",
    "analysis",
    "technical support",
    "professional services",
    "business services",
    "procurement",
}


def normalize_naics(value) -> str:
    """Normalize NAICS values, including CSV/database values such as 541611.0."""
    if value is None:
        return ""

    text = str(value).strip()

    if not text or text.lower() in {"nan", "none", "null"}:
        return ""

    if text.endswith(".0"):
        text = text[:-2]

    return text


def get_capability_documents(profile: dict) -> list[dict]:
    """Build separate reference documents for TTE competencies and experience."""
    documents = []

    for category, field in (
        ("Core Competency", "core_competencies"),
        ("Project Experience", "project_experience"),
    ):
        for item in profile.get(field, []):
            text = str(item).strip()

            if text:
                documents.append(
                    {
                        "category": category,
                        "capability": text,
                        "text": f"Tiger Team Engineering capability: {text}",
                    }
                )

    keyword_groups = profile.get("keyword_groups", {})

    if isinstance(keyword_groups, dict):
        for group_name, terms in keyword_groups.items():
            if isinstance(terms, str):
                terms = [terms]

            terms = [str(term).strip() for term in terms if str(term).strip()]

            if terms:
                documents.append(
                    {
                        "category": "Keyword Group",
                        "capability": str(group_name),
                        "text": (
                            f"Tiger Team Engineering capability area: "
                            f"{group_name}. Related terms: {', '.join(terms)}"
                        ),
                    }
                )

    elif isinstance(keyword_groups, list):
        for item in keyword_groups:
            if isinstance(item, dict):
                group_name = str(item.get("name", item.get("group", ""))).strip()
                terms = item.get("keywords", item.get("terms", []))

                if isinstance(terms, str):
                    terms = [terms]

                terms = [
                    str(term).strip()
                    for term in terms
                    if str(term).strip()
                ]

                if group_name or terms:
                    documents.append(
                        {
                            "category": "Keyword Group",
                            "capability": group_name or ", ".join(terms),
                            "text": (
                                f"Tiger Team Engineering capability area: "
                                f"{group_name}. Related terms: {', '.join(terms)}"
                            ),
                        }
                    )

    # Deduplicate documents without losing their categories.
    unique = []
    seen = set()

    for document in documents:
        key = (document["category"], document["capability"].lower())

        if key not in seen:
            seen.add(key)
            unique.append(document)

    if not unique:
        raise ValueError(
            "No TTE capability documents were found in company_profile.py."
        )

    return unique


def build_opportunity_text(opportunity: dict) -> str:
    """Combine available opportunity fields into a single text for matching."""
    fields = [
        opportunity.get("title"),
        opportunity.get("description"),
        opportunity.get("opportunity_type"),
        opportunity.get("solicitation_number"),
        opportunity.get("agency_name"),
        opportunity.get("set_aside_type"),
        opportunity.get("place_of_performance"),
    ]

    text = " ".join(
        str(value).strip()
        for value in fields
        if value is not None and str(value).strip()
        and str(value).strip().lower() not in {"nan", "none", "null"}
    )

    return text[:8000]


def get_direct_technical_evidence(text: str, profile: dict) -> tuple[list[str], list[str]]:
    """
    Find explicit capability-related keyword evidence.
    Generic terms by themselves do not count as technical evidence.
    """
    text_lower = text.lower()
    matched_groups = []
    matched_terms = []

    keyword_groups = profile.get("keyword_groups", {})

    if isinstance(keyword_groups, dict):
        group_items = keyword_groups.items()
    elif isinstance(keyword_groups, list):
        group_items = []

        for item in keyword_groups:
            if not isinstance(item, dict):
                continue

            group_name = item.get("name", item.get("group", ""))
            terms = item.get("keywords", item.get("terms", []))

            if isinstance(terms, str):
                terms = [terms]

            group_items.append((group_name, terms))
    else:
        group_items = []

    for group_name, terms in group_items:
        if isinstance(terms, str):
            terms = [terms]

        group_hits = []

        for term in terms:
            term = str(term).strip()
            term_lower = term.lower()

            if (
                len(term_lower) < 3
                or term_lower in GENERIC_TERMS
                or term_lower not in text_lower
            ):
                continue

            group_hits.append(term)

        if group_hits:
            matched_groups.append(str(group_name))
            matched_terms.extend(group_hits)

    # Also look for explicit phrases in TTE's stated competencies and experience.
    for field in ("core_competencies", "project_experience"):
        for item in profile.get(field, []):
            phrase = str(item).strip()

            if (
                phrase
                and phrase.lower() not in GENERIC_TERMS
                and phrase.lower() in text_lower
            ):
                matched_terms.append(phrase)

    # Preserve order and remove duplicates.
    matched_groups = list(dict.fromkeys(matched_groups))
    matched_terms = list(dict.fromkeys(matched_terms))

    return matched_groups, matched_terms


def classify_opportunity(opportunity: dict, naics_match: bool, text: str) -> tuple[str, str]:
    """Classify the record type and identify likely product-purchase listings."""
    title = str(opportunity.get("title") or "").strip()
    opportunity_type = str(opportunity.get("opportunity_type") or "").strip().lower()
    description = str(opportunity.get("description") or "").strip()

    if "award" in opportunity_type:
        return (
            "Award Notice",
            "Research Only - Award Notice",
        )

    if PRODUCT_TITLE_PATTERN.search(title):
        if naics_match:
            return (
                "Likely Product Purchase",
                "Manual Review - Product/Parts Listing",
            )

        return (
            "Likely Product Purchase",
            "Low Priority - Non-Target Product/Parts Listing",
        )

    if not description:
        return (
            "Insufficient Description",
            "Verify Official Notice - Missing Description",
        )

    if "presolicitation" in opportunity_type:
        return (
            "Presolicitation",
            "Monitor - Presolicitation",
        )

    if "sources sought" in opportunity_type or "sources sought" in title.lower():
        return (
            "Sources Sought",
            "Review - Sources Sought",
        )

    if "market research" in opportunity_type:
        return (
            "Market Research",
            "Research Only - Market Research",
        )

    if "solicitation" in opportunity_type:
        return (
            "Potential Solicitation",
            "Manual Technical Review",
        )

    return (
        "Unclassified",
        "Manual Review - Verify Opportunity Type",
    )


def determine_recommendation(
    opportunity: dict,
    naics_match: bool,
    semantic_similarity: float,
    matched_groups: list[str],
    matched_terms: list[str],
    record_classification: str,
    base_recommendation: str,
) -> tuple[str, str]:
    """
    Apply transparent review rules.
    No automatic bid/no-bid or eligibility decision is made.
    """
    opportunity_type = str(opportunity.get("opportunity_type") or "").lower()
    description = str(opportunity.get("description") or "").strip()
    title = str(opportunity.get("title") or "").strip()

    if "award" in opportunity_type:
        return (
            "Research Only - Award Notice",
            "Award notices are not treated as open bidding opportunities.",
        )

    if not description:
        return (
            "Verify Official Notice - Missing Description",
            "Description is missing; technical relevance cannot be established.",
        )

    if record_classification == "Likely Product Purchase":
        if not naics_match:
            return (
                "Low Priority - Non-Target Product/Parts Listing",
                "Likely product purchase with a non-target NAICS code.",
            )

        return (
            "Manual Review - Product/Parts Listing",
            "Target NAICS match does not establish that TTE can supply the item.",
        )

    if "presolicitation" in opportunity_type:
        return (
            "Monitor - Presolicitation",
            "Monitor for the final solicitation and verify the expected requirements.",
        )

    if not naics_match:
        if matched_groups and semantic_similarity >= SEMANTIC_STRONG_THRESHOLD:
            return (
                "Exception Review - Non-Target NAICS",
                "Some technical evidence exists, but the NAICS code is outside TTE's target list.",
            )

        return (
            "Low Priority - Non-Target NAICS",
            "No target NAICS match and insufficient evidence for an exception review.",
        )

    if (
        matched_groups
        and semantic_similarity >= SEMANTIC_REVIEW_THRESHOLD
    ):
        return (
            "High-Priority Human Review",
            "Target NAICS match plus direct capability-related keyword evidence and semantic relevance.",
        )

    if semantic_similarity >= SEMANTIC_REVIEW_THRESHOLD:
        return (
            "Manual Technical Review",
            "Target NAICS match and semantic relevance, but direct technical evidence is limited.",
        )

    return (
        "Manual Review - Weak Technical Match",
        "Target NAICS match exists, but the current technical evidence is weak.",
    )


def main() -> None:
    print("=" * 88)
    print("TTE SEMANTIC MATCHER V2 - READ-ONLY EXPERIMENT")
    print("=" * 88)

    profile = get_company_profile()
    target_naics = {
        normalize_naics(code)
        for code in profile.get("target_naics_codes", [])
        if normalize_naics(code)
    }

    print(f"Company: {profile.get('company_name', 'Tiger Team Engineering')}")
    print(f"Target NAICS codes: {', '.join(sorted(target_naics))}")
    print(f"Model: {MODEL_NAME}")
    print("Database writes: NONE")
    print("Production engine modifications: NONE")
    print()

    capability_documents = get_capability_documents(profile)
    print(f"Capability reference documents: {len(capability_documents)}")

    print("Loading cached sentence-embedding model...")
    model = SentenceTransformer(
        MODEL_NAME,
        local_files_only=True,
    )

    capability_texts = [item["text"] for item in capability_documents]
    capability_embeddings = model.encode(
        capability_texts,
        convert_to_numpy=True,
        normalize_embeddings=True,
        show_progress_bar=False,
    )

    print("Loading real opportunities...")
    opportunities = load_opportunities_for_qualification(include_samples=False)
    print(f"Real opportunities loaded: {len(opportunities)}")

    rows = []

    for index, opportunity in enumerate(opportunities, start=1):
        text = build_opportunity_text(opportunity)
        title = str(opportunity.get("title") or "").strip()
        naics_code = normalize_naics(opportunity.get("naics_code"))
        naics_match = bool(naics_code and naics_code in target_naics)

        matched_groups, matched_terms = get_direct_technical_evidence(
            text,
            profile,
        )

        if text.strip():
            opportunity_embedding = model.encode(
                [text],
                convert_to_numpy=True,
                normalize_embeddings=True,
                show_progress_bar=False,
            )

            similarities = cosine_similarity(
                opportunity_embedding,
                capability_embeddings,
            )[0]

            best_indices = np.argsort(similarities)[::-1]
            best_index = int(best_indices[0])
            best_similarity = float(similarities[best_index])

            second_index = int(best_indices[1]) if len(best_indices) > 1 else best_index
            third_index = int(best_indices[2]) if len(best_indices) > 2 else second_index

            second_similarity = float(similarities[second_index])
            third_similarity = float(similarities[third_index])

            best_capability = capability_documents[best_index]
            second_capability = capability_documents[second_index]
            third_capability = capability_documents[third_index]
        else:
            best_similarity = 0.0
            second_similarity = 0.0
            third_similarity = 0.0
            best_capability = {
                "capability": "",
                "category": "",
            }
            second_capability = {
                "capability": "",
                "category": "",
            }
            third_capability = {
                "capability": "",
                "category": "",
            }

        record_classification, base_recommendation = classify_opportunity(
            opportunity,
            naics_match,
            text,
        )

        recommendation, rationale = determine_recommendation(
            opportunity=opportunity,
            naics_match=naics_match,
            semantic_similarity=best_similarity,
            matched_groups=matched_groups,
            matched_terms=matched_terms,
            record_classification=record_classification,
            base_recommendation=base_recommendation,
        )

        rows.append(
            {
                "opportunity_id": opportunity.get("opportunity_id", ""),
                "title": title,
                "agency_name": opportunity.get("agency_name", ""),
                "opportunity_type": opportunity.get("opportunity_type", ""),
                "naics_code": naics_code,
                "target_naics_match": naics_match,
                "record_classification": record_classification,
                "semantic_similarity": round(best_similarity, 4),
                "best_capability": best_capability["capability"],
                "best_capability_category": best_capability["category"],
                "second_capability": second_capability["capability"],
                "second_similarity": round(second_similarity, 4),
                "third_capability": third_capability["capability"],
                "third_similarity": round(third_similarity, 4),
                "direct_evidence_group_count": len(matched_groups),
                "direct_evidence_groups": "; ".join(matched_groups),
                "direct_evidence_terms": "; ".join(matched_terms),
                "recommendation": recommendation,
                "recommendation_rationale": rationale,
                "response_deadline": opportunity.get("response_deadline", ""),
                "set_aside_type": opportunity.get("set_aside_type", ""),
                "source_url": opportunity.get("source_url", ""),
                "review_note": (
                    "Exploratory assessment only. Verify the official notice, "
                    "current deadline, requirements, and eligibility."
                ),
            }
        )

        if index % 10 == 0 or index == len(opportunities):
            print(f"Processed {index}/{len(opportunities)} opportunities...")

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = list(rows[0].keys()) if rows else [
        "opportunity_id",
        "title",
        "recommendation",
    ]

    with OUTPUT_FILE.open("w", newline="", encoding="utf-8-sig") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print()
    print("=" * 88)
    print("V2 RECOMMENDATION SUMMARY")
    print("=" * 88)

    counts = {}

    for row in rows:
        label = row["recommendation"]
        counts[label] = counts.get(label, 0) + 1

    for label, count in sorted(counts.items(), key=lambda item: (-item[1], item[0])):
        print(f"{label}: {count}")

    target_matches = sum(1 for row in rows if row["target_naics_match"])
    high_priority = [
        row for row in rows
        if row["recommendation"] == "High-Priority Human Review"
    ]

    print()
    print(f"Total records evaluated: {len(rows)}")
    print(f"Exact target NAICS matches: {target_matches}")
    print(f"High-priority human-review records: {len(high_priority)}")
    print()
    print("TOP 15 BY V2 REVIEW PRIORITY")
    print("-" * 88)

    priority_order = {
        "High-Priority Human Review": 1,
        "Manual Technical Review": 2,
        "Exception Review - Non-Target NAICS": 3,
        "Manual Review - Weak Technical Match": 4,
        "Manual Review - Product/Parts Listing": 5,
        "Monitor - Presolicitation": 6,
        "Review - Sources Sought": 7,
        "Research Only - Market Research": 8,
        "Research Only - Award Notice": 9,
        "Verify Official Notice - Missing Description": 10,
        "Low Priority - Non-Target NAICS": 11,
        "Low Priority - Non-Target Product/Parts Listing": 12,
    }

    ranked_rows = sorted(
        rows,
        key=lambda row: (
            priority_order.get(row["recommendation"], 99),
            not row["target_naics_match"],
            -row["semantic_similarity"],
            -row["direct_evidence_group_count"],
        ),
    )

    for row in ranked_rows[:15]:
        print(
            f"ID {row['opportunity_id']} | "
            f"NAICS {row['naics_code'] or 'MISSING'} | "
            f"Target match: {row['target_naics_match']} | "
            f"Similarity: {row['semantic_similarity']:.4f}"
        )
        print(f"  Title: {row['title']}")
        print(f"  Type: {row['record_classification']}")
        print(f"  Recommendation: {row['recommendation']}")
        print(f"  Best capability: {row['best_capability']}")
        print(f"  Evidence groups: {row['direct_evidence_groups'] or 'None found'}")
        print(f"  Reason: {row['recommendation_rationale']}")
        print("-" * 88)

    print()
    print(f"CSV report saved to: {OUTPUT_FILE.resolve()}")
    print("Database records modified: NONE")
    print("Production scoring logic changed: NO")
    print(
        "Reminder: recommendations are preliminary human-review priorities, "
        "not eligibility determinations or bid-success probabilities."
    )


if __name__ == "__main__":
    main()
