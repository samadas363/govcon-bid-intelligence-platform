import argparse
import csv
import re
from pathlib import Path
from datetime import datetime


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPORTS_DIR = PROJECT_ROOT / "data" / "reports"

SPECIALIZED_TERMS = {
    "weapons_and_defense_systems": [
        "weapon system", "missile", "avenger weapon",
        "aegis", "combat system", "defense system",
        "special operations forces", "sof-t"
    ],
    "intelligence_and_surveillance": [
        "intelligence analysis", "synthetic aperture radar",
        "surveillance", "signals intelligence",
        "intelligence systems"
    ],
    "healthcare_and_clinical": [
        "clinical quality", "credentialing",
        "privileging", "pharmacy inventory",
        "medical services", "healthcare"
    ],
    "specialized_construction": [
        "medium voltage", "transformers",
        "roof replacement", "electrical feeder",
        "hazardous material abatement"
    ],
    "specialized_aerospace": [
        "aircraft radar", "aerospace systems",
        "flight testing", "aircraft weapons",
        "aircraft sustainment"
    ]
}

TTE_CAPABILITY_GROUPS = {
    "engineering",
    "supply_chain",
    "procurement",
    "logistics",
    "analytics_and_risk",
    "delivery_and_production",
    "staffing",
    "management_consulting"
}


def get_value(row, *names, default=""):
    """Return the first available non-empty CSV field."""
    for name in names:
        value = row.get(name)
        if value is not None and str(value).strip():
            return str(value).strip()
    return default


def to_number(value, default=0):
    try:
        return float(str(value).replace(",", "").strip())
    except (ValueError, TypeError):
        return default


def parse_groups(value):
    """Parse matched technical groups from the V2 output."""
    if not value:
        return set()

    return {
        item.strip().lower()
        for item in re.split(r"[,;|]", value)
        if item.strip()
    }


def detect_specialized_indicators(text):
    text = text.lower()
    matches = []

    for category, terms in SPECIALIZED_TERMS.items():
        found = [term for term in terms if term in text]

        if found:
            matches.append(
                f"{category}: {', '.join(found)}"
            )

    return matches


def classify_opportunity(row):
    title = get_value(row, "title")
    description = get_value(
        row,
        "description_text",
        "description",
        "notice_description"
    )

    combined_text = f"{title} {description}".lower()

    relevance_score = to_number(
        get_value(row, "relevance_v2_score")
    )

    naics_score = to_number(
        get_value(row, "v2_naics_score")
    )

    technical_score = to_number(
        get_value(row, "v2_technical_score")
    )

    evidence_score = to_number(
        get_value(row, "v2_description_evidence_score")
    )

    groups = parse_groups(
        get_value(row, "v2_technical_matched_groups")
    )

    matched_groups = sorted(groups & TTE_CAPABILITY_GROUPS)

    description_status = get_value(
        row,
        "v2_description_evidence_status",
        "description_status"
    ).lower()

    procurement_stage = get_value(
        row,
        "v2_procurement_stage"
    )

    specialized = detect_specialized_indicators(combined_text)

    # Evidence checks
    description_available = bool(description.strip())

    evidence_sufficient = (
        description_available
        and evidence_score >= 10
    )

    technical_alignment = len(matched_groups)

    # Default classification
    classification = "Insufficient Evidence"
    confidence = "Low"
    reason = ""
    action = "Obtain the full solicitation, SOW, and additional evidence."

    # Rule 1: Missing or inadequate evidence
    if not description_available or evidence_score < 10:
        classification = "Insufficient Evidence"
        confidence = "Low"
        reason = (
            "Description or supporting evidence is insufficient "
            "for a reliable capability assessment."
        )
        action = (
            "Retrieve the complete notice description, SOW, "
            "and technical requirements."
        )

    # Rule 2: Specialized work with no identified TTE capability bridge
    elif specialized and technical_alignment == 0:
        classification = "Specialized Opportunity"
        confidence = "Medium"
        reason = (
            "Specialized technical requirements were detected, "
            "but no matching TTE capability group was identified."
        )
        action = (
            "Review only if TTE has relevant past performance "
            "or can identify a qualified specialist partner."
        )

    # Rule 3: Specialized work with some TTE capability overlap
    elif specialized and technical_alignment >= 1:
        classification = "Teaming Opportunity"
        confidence = "Medium"
        reason = (
            "Specialized requirements were detected alongside "
            "potential TTE capability overlap."
        )
        action = (
            "Investigate prime contractors and potential teaming "
            "arrangements. Verify TTE's specific workshare."
        )

    # Rule 4: Strict direct opportunity criteria
    elif (
        relevance_score >= 80
        and naics_score >= 25
        and technical_alignment >= 2
        and evidence_score >= 15
    ):
        classification = "Direct TTE Opportunity"
        confidence = "High"
        reason = (
            "Strong relevance score, target NAICS alignment, "
            "multiple technical capability matches, and "
            "sufficient description evidence."
        )
        action = (
            "Review eligibility, SOW, past performance, "
            "staffing, deadlines, and proposal requirements."
        )

    # Rule 5: Potential direct opportunity
    elif (
        relevance_score >= 60
        and naics_score >= 20
        and technical_alignment >= 1
        and evidence_score >= 15
    ):
        classification = "Potential Direct Opportunity"
        confidence = "Medium"
        reason = (
            "The opportunity has target NAICS alignment, "
            "at least one matching TTE capability group, "
            "and sufficient description evidence."
        )
        action = (
            "Review the complete SOW, technical requirements, "
            "eligibility, and TTE past performance."
        )

    # Rule 6: Some alignment, but not enough for direct classification
    elif (
        relevance_score >= 45
        and technical_alignment >= 1
        and evidence_sufficient
    ):
        classification = "Potential Direct Opportunity"
        confidence = "Low"
        reason = (
            "Some TTE capability alignment exists, but the "
            "available evidence does not support a stronger rating."
        )
        action = (
            "Perform manual capability and requirements review "
            "before considering this opportunity for bidding."
        )

    else:
        classification = "Insufficient Evidence"
        confidence = "Low"
        reason = (
            "Available evidence does not establish sufficient "
            "alignment with TTE's documented capabilities."
        )
        action = (
            "Conduct manual review or obtain additional "
            "solicitation information."
        )

    return {
        "bd_classification": classification,
        "bd_confidence": confidence,
        "bd_classification_reason": reason,
        "bd_recommended_action": action,
        "bd_matched_tte_groups": ", ".join(matched_groups),
        "bd_specialized_indicators": " | ".join(specialized),
        "bd_relevance_score_used": relevance_score,
        "bd_evidence_score_used": evidence_score,
        "bd_technical_groups_count": technical_alignment,
        "bd_procurement_stage": procurement_stage,
        "bd_description_available": description_available,
        "bd_manual_review_required": (
            classification != "Direct TTE Opportunity"
        )
    }


def find_latest_input():
    files = list(
        REPORTS_DIR.glob("sam_opportunity_relevance_v2_*.csv")
    )

    if not files:
        raise FileNotFoundError(
            f"No V2 relevance report found in {REPORTS_DIR}"
        )

    return max(files, key=lambda file: file.stat().st_mtime)


def main():
    parser = argparse.ArgumentParser(
        description="TTE Business Development Classification Engine"
    )

    parser.add_argument(
        "--input",
        type=str,
        help="Optional input V2 CSV report"
    )

    args = parser.parse_args()

    input_file = (
        Path(args.input).resolve()
        if args.input
        else find_latest_input()
    )

    if not input_file.exists():
        raise FileNotFoundError(
            f"Input report not found: {input_file}"
        )

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    output_file = (
        REPORTS_DIR
        / f"sam_opportunity_bd_classification_{timestamp}.csv"
    )

    print("\nTTE BUSINESS DEVELOPMENT CLASSIFICATION ENGINE")
    print("=" * 55)
    print(f"Input:  {input_file.name}")
    print(f"Output: {output_file.name}")
    print("Database: NOT CONNECTED")
    print("=" * 55)

    with input_file.open(
        "r",
        encoding="utf-8-sig",
        newline=""
    ) as source:

        reader = csv.DictReader(source)

        if not reader.fieldnames:
            raise ValueError("Input CSV has no column headers.")

        original_fields = reader.fieldnames
        new_fields = [
            "bd_classification",
            "bd_confidence",
            "bd_classification_reason",
            "bd_recommended_action",
            "bd_matched_tte_groups",
            "bd_specialized_indicators",
            "bd_relevance_score_used",
            "bd_evidence_score_used",
            "bd_technical_groups_count",
            "bd_procurement_stage",
            "bd_description_available",
            "bd_manual_review_required"
        ]

        output_fields = original_fields + [
            field for field in new_fields
            if field not in original_fields
        ]

        counts = {}
        total = 0

        output_file.parent.mkdir(
            parents=True,
            exist_ok=True
        )

        with output_file.open(
            "w",
            encoding="utf-8-sig",
            newline=""
        ) as destination:

            writer = csv.DictWriter(
                destination,
                fieldnames=output_fields,
                extrasaction="ignore"
            )

            writer.writeheader()

            for row in reader:
                result = classify_opportunity(row)
                row.update(result)
                writer.writerow(row)

                category = result["bd_classification"]
                counts[category] = counts.get(category, 0) + 1
                total += 1

    print("\nCLASSIFICATION SUMMARY")
    print("-" * 40)
    print(f"Total opportunities: {total}")

    categories = [
        "Direct TTE Opportunity",
        "Potential Direct Opportunity",
        "Teaming Opportunity",
        "Specialized Opportunity",
        "Insufficient Evidence"
    ]

    for category in categories:
        count = counts.get(category, 0)
        percentage = (
            (count / total) * 100
            if total else 0
        )

        print(
            f"{category}: {count} ({percentage:.1f}%)"
        )

    print("\nSUCCESS: Classification completed.")
    print(f"Report saved to: {output_file}")
    print("Original input report was not modified.")
    print("PostgreSQL was not accessed.")


if __name__ == "__main__":
    main()
