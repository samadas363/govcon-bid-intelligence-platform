import argparse
import csv
import re
from datetime import datetime
from pathlib import Path

from src.qualification_engine import TARGET_NAICS, KEYWORD_GROUPS


ROOT_DIR = Path(__file__).resolve().parent.parent
REPORT_DIR = ROOT_DIR / "data" / "reports"


def normalize(value):
    if value is None:
        return ""
    return str(value).strip()


def flatten_keywords(value):
    """Extract keyword strings from nested dictionaries, lists, or tuples."""
    results = []

    if isinstance(value, dict):
        for item in value.values():
            results.extend(flatten_keywords(item))
    elif isinstance(value, (list, tuple, set)):
        for item in value:
            results.extend(flatten_keywords(item))
    elif isinstance(value, str):
        text = value.strip().lower()
        if len(text) >= 3:
            results.append(text)

    return results


def find_latest_input():
    files = list(REPORT_DIR.glob("sam_opportunity_prioritization_*.csv"))

    if not files:
        raise FileNotFoundError(
            "No prioritization CSV found in data/reports."
        )

    return max(files, key=lambda path: path.stat().st_mtime)


def contains_phrase(text, phrase):
    """Match a keyword or phrase without matching inside unrelated words."""
    if not text or not phrase:
        return False

    pattern = r"(?<![a-z0-9])" + re.escape(phrase.lower()) + r"(?![a-z0-9])"
    return re.search(pattern, text.lower()) is not None


def parse_naics(value):
    return re.sub(r"\D", "", normalize(value))


def score_opportunity(row, keyword_groups, target_naics):
    title = normalize(row.get("title"))
    description = normalize(row.get("description_text"))
    notice_type = normalize(row.get("notice_type"))
    classification = normalize(row.get("opportunity_classification"))

    full_text = f"{title} {description}".lower()
    title_text = title.lower()
    description_text = description.lower()

    # ---------------------------------------------------------
    # 1. NAICS alignment: maximum 40 points
    # ---------------------------------------------------------
    naics_code = parse_naics(row.get("naics_code"))
    target_codes = {parse_naics(code) for code in target_naics}

    matched_naics_value = normalize(row.get("matched_target_naics")).lower()
    existing_naics_match = normalize(row.get("naics_match")).lower()

    naics_match = (
        naics_code in target_codes
        or matched_naics_value in {"true", "yes", "1"}
        or existing_naics_match in {"true", "yes", "1", "exact match"}
    )

    naics_score = 40 if naics_match else 0

    # ---------------------------------------------------------
    # 2. Technical keyword alignment: maximum 30 points
    # ---------------------------------------------------------
    matched_groups = []
    matched_keywords = []

    for group_name, keywords in keyword_groups.items():
        group_hits = []

        for keyword in keywords:
            if contains_phrase(full_text, keyword):
                group_hits.append(keyword)

        if group_hits:
            matched_groups.append(str(group_name))
            matched_keywords.extend(group_hits)

    matched_keywords = sorted(set(matched_keywords))

    # Reward distinct capability areas, not repeated keyword mentions.
    technical_score = min(30, len(matched_groups) * 10)

    # ---------------------------------------------------------
    # 3. Capability alignment: maximum 20 points
    # ---------------------------------------------------------
    title_hits = [
        keyword for keyword in matched_keywords
        if contains_phrase(title_text, keyword)
    ]

    description_hits = [
        keyword for keyword in matched_keywords
        if contains_phrase(description_text, keyword)
    ]

    capability_score = min(
        20,
        (len(set(title_hits)) * 5) +
        (len(set(description_hits)) * 2)
    )

    # ---------------------------------------------------------
    # 4. Description evidence: maximum 10 points
    # ---------------------------------------------------------
    if not description:
        evidence_score = 0
        evidence_status = "Description Missing"
    elif len(description.strip()) < 100:
        evidence_score = 3
        evidence_status = "Limited Description"
    elif description_hits:
        evidence_score = 10
        evidence_status = "Technical Evidence Found"
    else:
        evidence_score = 5
        evidence_status = "Description Available; No TTE Keywords Found"

    relevance_score = (
        naics_score +
        technical_score +
        capability_score +
        evidence_score
    )

    # ---------------------------------------------------------
    # 5. Relevance classification
    # ---------------------------------------------------------
    if not description and not matched_groups and not naics_match:
        relevance_category = "Insufficient Evidence"
    elif relevance_score >= 70 and (naics_match or matched_groups):
        relevance_category = "Strong Fit"
    elif relevance_score >= 40 and (naics_match or matched_groups):
        relevance_category = "Possible Fit"
    else:
        relevance_category = "Weak Fit"

    # ---------------------------------------------------------
    # 6. Relevance explanation
    # ---------------------------------------------------------
    reasons = []

    if naics_match:
        reasons.append("Target NAICS alignment identified")
    else:
        reasons.append("No exact target NAICS match identified")

    if matched_groups:
        reasons.append(
            "Technical areas matched: " + ", ".join(matched_groups)
        )
    else:
        reasons.append("No configured TTE technical keyword groups matched")

    reasons.append(evidence_status)

    relevance_reason = "; ".join(reasons)

    # ---------------------------------------------------------
    # 7. Recommended action
    # ---------------------------------------------------------
    priority = normalize(row.get("priority_level")).upper()
    opportunity_class = (
        normalize(row.get("engine_opportunity_category"))
        or classification
        or notice_type
    ).lower()

    if "award" in opportunity_class:
        recommended_action = "Research Only - Award Notice"
    elif relevance_category == "Insufficient Evidence":
        recommended_action = "Manual Review - Obtain Full Description"
    elif relevance_category == "Weak Fit":
        recommended_action = "Low Priority - Verify Scope Before Pursuing"
    elif relevance_category == "Strong Fit" and priority == "P1":
        recommended_action = "Immediate Review - Urgent and Strong Fit"
    elif relevance_category == "Strong Fit":
        recommended_action = "Prioritize for Detailed Evaluation"
    elif relevance_category == "Possible Fit" and priority == "P1":
        recommended_action = "Urgent Review - Confirm Technical Alignment"
    elif relevance_category == "Possible Fit":
        recommended_action = "Review Solicitation and Capability Requirements"
    else:
        recommended_action = "Manual Review"

    return {
        "relevance_score": relevance_score,
        "relevance_maximum_score": 100,
        "relevance_category": relevance_category,
        "relevance_naics_score": naics_score,
        "relevance_technical_score": technical_score,
        "relevance_capability_score": capability_score,
        "relevance_evidence_score": evidence_score,
        "relevance_matched_groups": "; ".join(matched_groups),
        "relevance_matched_keywords": "; ".join(matched_keywords),
        "relevance_reason": relevance_reason,
        "relevance_recommended_action": recommended_action,
        "relevance_review_required": (
            "Yes" if relevance_category != "Strong Fit" else "No"
        ),
    }


def main():
    parser = argparse.ArgumentParser(
        description="Assess TTE relevance of prioritized SAM.gov opportunities."
    )

    parser.add_argument(
        "--input",
        type=str,
        help="Optional path to a prioritization CSV."
    )

    args = parser.parse_args()

    input_file = (
        Path(args.input).resolve()
        if args.input
        else find_latest_input()
    )

    if not input_file.exists():
        raise FileNotFoundError(f"Input file not found: {input_file}")

    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    keyword_groups = {
        str(group): flatten_keywords(keywords)
        for group, keywords in KEYWORD_GROUPS.items()
    }

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    output_file = REPORT_DIR / (
        f"sam_opportunity_relevance_{timestamp}.csv"
    )

    with input_file.open(
        "r", encoding="utf-8-sig", newline=""
    ) as source:
        reader = csv.DictReader(source)

        if not reader.fieldnames:
            raise ValueError("Input CSV has no column headers.")

        original_fields = reader.fieldnames
        rows = list(reader)

    results = []

    for row in rows:
        try:
            assessment = score_opportunity(
                row,
                keyword_groups,
                TARGET_NAICS
            )
            results.append({**row, **assessment})
        except Exception as exc:
            results.append({
                **row,
                "relevance_score": 0,
                "relevance_maximum_score": 100,
                "relevance_category": "Assessment Error",
                "relevance_reason": str(exc),
                "relevance_recommended_action": "Manual Review",
                "relevance_review_required": "Yes",
            })

    new_fields = [
        "relevance_score",
        "relevance_maximum_score",
        "relevance_category",
        "relevance_naics_score",
        "relevance_technical_score",
        "relevance_capability_score",
        "relevance_evidence_score",
        "relevance_matched_groups",
        "relevance_matched_keywords",
        "relevance_reason",
        "relevance_recommended_action",
        "relevance_review_required",
    ]

    output_fields = list(original_fields)

    for field in new_fields:
        if field not in output_fields:
            output_fields.append(field)

    with output_file.open(
        "w", encoding="utf-8-sig", newline=""
    ) as destination:
        writer = csv.DictWriter(
            destination,
            fieldnames=output_fields,
            extrasaction="ignore"
        )
        writer.writeheader()
        writer.writerows(results)

    # ---------------------------------------------------------
    # Summary
    # ---------------------------------------------------------
    print("\n" + "=" * 65)
    print("TTE OPPORTUNITY RELEVANCE ENGINE")
    print("=" * 65)

    print(f"Input file: {input_file.name}")
    print(f"Total opportunities: {len(results)}")

    categories = {}

    for row in results:
        category = row.get("relevance_category", "Unknown")
        categories[category] = categories.get(category, 0) + 1

    print("\nRELEVANCE CLASSIFICATION")
    print("-" * 40)

    for category, count in sorted(categories.items()):
        print(f"{category}: {count}")

    print("\nOUTPUT FILE")
    print("-" * 40)
    print(output_file)

    print("\nPostgreSQL accessed: NO")
    print("Existing reports modified: NO")
    print("Existing qualification scores modified: NO")
    print("Existing prioritization scores modified: NO")

    print("\nRelevance assessment completed.")


if __name__ == "__main__":
    main()
