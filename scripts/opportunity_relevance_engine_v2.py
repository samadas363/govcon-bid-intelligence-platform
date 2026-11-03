import argparse
import csv
import re
import sys
from datetime import datetime
from pathlib import Path


# ---------------------------------------------------------
# PROJECT PATHS AND IMPORTS
# ---------------------------------------------------------

ROOT_DIR = Path(__file__).resolve().parent.parent
REPORT_DIR = ROOT_DIR / "data" / "reports"

if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.qualification_engine import TARGET_NAICS, KEYWORD_GROUPS


# ---------------------------------------------------------
# V2 SCORING CONFIGURATION
# ---------------------------------------------------------

MAX_NAICS_SCORE = 25
MAX_TECHNICAL_SCORE = 35
MAX_DESCRIPTION_SCORE = 30
MAX_STAGE_SCORE = 10

STRONG_FIT_THRESHOLD = 80
POSSIBLE_FIT_THRESHOLD = 60
WEAK_FIT_THRESHOLD = 35


# Terms indicating actual scope or work activities.
SCOPE_TERMS = [
    "engineering",
    "technical support",
    "technical services",
    "management support",
    "project management",
    "program management",
    "supply chain",
    "procurement",
    "logistics",
    "supplier management",
    "supplier oversight",
    "quality management",
    "performance management",
    "risk assessment",
    "data analysis",
    "analytics",
    "continuous improvement",
    "production support",
    "delivery management",
    "technical assessment",
    "special studies",
    "operational support",
    "research and development",
    "research and test",
]

# Terms indicating that the description contains useful
# contractual requirements or deliverables.
REQUIREMENT_TERMS = [
    "statement of work",
    "scope of work",
    "deliverables",
    "performance work statement",
    "personnel qualifications",
    "key personnel",
    "minimum qualifications",
    "technical requirements",
    "performance standards",
    "quality assurance",
    "period of performance",
    "staffing requirements",
    "contractor shall",
    "the contractor will",
    "required experience",
    "past performance",
]

# Requirements that need human verification.
SPECIAL_REQUIREMENT_TERMS = [
    "security clearance",
    "secret clearance",
    "top secret",
    "top-secret",
    "facility clearance",
    "certified professional",
    "professional license",
    "licensed engineer",
    "registered professional engineer",
    "oem certification",
    "manufacturer authorization",
    "cmmc",
    "cmmc level",
    "cmmc certification",
    "fedramp",
    "hipaa",
    "iso 27001",
    "iso 9001",
    "specific clearance",
    "active clearance",
    "us citizenship required",
]

# Terms identifying notices that are not ordinary competitive
# bidding opportunities.
NONCOMPETITIVE_TERMS = [
    "intent to award",
    "notice of intent to award",
    "not a request for competitive proposals",
    "not a request for proposals",
    "sole source",
    "single source",
]

AWARD_TERMS = [
    "award notice",
    "award notification",
    "contract award",
]


# ---------------------------------------------------------
# GENERAL HELPERS
# ---------------------------------------------------------

def clean(value):
    if value is None:
        return ""
    return str(value).strip()


def normalize_text(value):
    return re.sub(r"\s+", " ", clean(value).lower())


def contains_phrase(text, phrase):
    if not text or not phrase:
        return False

    pattern = (
        r"(?<![a-z0-9])"
        + re.escape(phrase.lower())
        + r"(?![a-z0-9])"
    )

    return re.search(pattern, text.lower()) is not None


def flatten_keywords(value):
    results = []

    if isinstance(value, dict):
        for item in value.values():
            results.extend(flatten_keywords(item))

    elif isinstance(value, (list, tuple, set)):
        for item in value:
            results.extend(flatten_keywords(item))

    elif isinstance(value, str):
        keyword = value.strip().lower()

        if len(keyword) >= 3:
            results.append(keyword)

    return sorted(set(results))


def parse_naics(value):
    return re.sub(r"\D", "", clean(value))


def find_latest_input():
    files = list(
        REPORT_DIR.glob("sam_opportunity_prioritization_*.csv")
    )

    if not files:
        raise FileNotFoundError(
            "No prioritization CSV found in data/reports."
        )

    return max(files, key=lambda path: path.stat().st_mtime)


# ---------------------------------------------------------
# 1. NAICS ALIGNMENT: 25 POINTS
# ---------------------------------------------------------

def score_naics(row, target_naics):
    opportunity_naics = parse_naics(row.get("naics_code"))

    target_codes = {
        parse_naics(code)
        for code in target_naics
    }

    matched_value = normalize_text(
        row.get("matched_target_naics")
    )

    existing_match = normalize_text(
        row.get("naics_match")
    )

    exact_match = (
        opportunity_naics in target_codes
        or matched_value in {"true", "yes", "1"}
        or existing_match in {
            "true",
            "yes",
            "1",
            "exact match",
        }
    )

    return {
        "score": MAX_NAICS_SCORE if exact_match else 0,
        "matched": exact_match,
        "opportunity_naics": opportunity_naics,
    }


# ---------------------------------------------------------
# 2. TECHNICAL CAPABILITY ALIGNMENT: 35 POINTS
# ---------------------------------------------------------

def score_technical(description, keyword_groups):
    matched_groups = []
    matched_keywords = []

    # Only the description counts as technical evidence.
    # Title-only matches are reported separately.
    for group_name, keywords in keyword_groups.items():

        group_hits = []

        for keyword in keywords:
            if contains_phrase(description, keyword):
                group_hits.append(keyword)

        if group_hits:
            matched_groups.append(group_name)
            matched_keywords.extend(group_hits)

    matched_groups = sorted(set(matched_groups))
    matched_keywords = sorted(set(matched_keywords))

    # Each distinct capability group contributes 7 points.
    score = min(
        MAX_TECHNICAL_SCORE,
        len(matched_groups) * 7
    )

    return {
        "score": score,
        "matched_groups": matched_groups,
        "matched_keywords": matched_keywords,
    }


# ---------------------------------------------------------
# 3. DESCRIPTION EVIDENCE: 30 POINTS
# ---------------------------------------------------------

def score_description_evidence(description):
    if not description:
        return {
            "score": 0,
            "status": "Description Missing",
            "scope_matches": [],
            "requirement_matches": [],
        }

    text = normalize_text(description)

    # A. Description availability and detail: 0-10
    if len(text) >= 1500:
        detail_score = 10
    elif len(text) >= 750:
        detail_score = 8
    elif len(text) >= 300:
        detail_score = 6
    elif len(text) >= 100:
        detail_score = 4
    else:
        detail_score = 2

    # B. Actual scope language: 0-10
    scope_matches = [
        term for term in SCOPE_TERMS
        if contains_phrase(text, term)
    ]

    scope_score = min(
        10,
        len(scope_matches) * 2
    )

    # C. Requirements and deliverables: 0-10
    requirement_matches = [
        term for term in REQUIREMENT_TERMS
        if contains_phrase(text, term)
    ]

    requirement_score = min(
        10,
        len(requirement_matches) * 2
    )

    total = (
        detail_score +
        scope_score +
        requirement_score
    )

    return {
        "score": min(MAX_DESCRIPTION_SCORE, total),
        "status": "Description Available",
        "scope_matches": scope_matches,
        "requirement_matches": requirement_matches,
    }


# ---------------------------------------------------------
# 4. PROCUREMENT STAGE: 10 POINTS
# ---------------------------------------------------------

def score_procurement_stage(row):
    notice_type = normalize_text(row.get("notice_type"))
    classification = normalize_text(
        row.get("opportunity_classification")
    )

    combined = f"{notice_type} {classification}"

    if "award" in combined:
        return {
            "score": 0,
            "stage": "Award Notice",
        }

    if "solicitation" in combined:
        return {
            "score": 10,
            "stage": "Active Solicitation",
        }

    if "sources sought" in combined:
        return {
            "score": 8,
            "stage": "Market Research",
        }

    if "request for information" in combined or re.search(
        r"\brfi\b", combined
    ):
        return {
            "score": 8,
            "stage": "Request for Information",
        }

    if "presolicitation" in combined:
        return {
            "score": 6,
            "stage": "Presolicitation",
        }

    if "special notice" in combined:
        return {
            "score": 3,
            "stage": "Special Notice",
        }

    return {
        "score": 2,
        "stage": "Other / Manual Review",
    }


# ---------------------------------------------------------
# 5. SPECIAL REQUIREMENTS
# ---------------------------------------------------------

def identify_special_requirements(text):
    matches = [
        term for term in SPECIAL_REQUIREMENT_TERMS
        if contains_phrase(text, term)
    ]

    return sorted(set(matches))


# ---------------------------------------------------------
# 6. OPPORTUNITY PURSUIT STATUS
# ---------------------------------------------------------

def determine_pursuit_status(row):
    combined = normalize_text(
        " ".join([
            clean(row.get("title")),
            clean(row.get("notice_type")),
            clean(row.get("opportunity_classification")),
            clean(row.get("manual_review_reason")),
        ])
    )

    if any(
        contains_phrase(combined, term)
        for term in AWARD_TERMS
    ) or "award notice" in combined:
        return "Research Only - Award Notice"

    if any(
        contains_phrase(combined, term)
        for term in NONCOMPETITIVE_TERMS
    ):
        return "Noncompetitive / Not an Open Bid"

    return "Review Official Notice"


# ---------------------------------------------------------
# 7. COMPLETE V2 RELEVANCE ASSESSMENT
# ---------------------------------------------------------

def assess_opportunity(row, keyword_groups, target_naics):
    title = clean(row.get("title"))
    description = clean(row.get("description_text"))

    full_text = f"{title} {description}"

    naics = score_naics(row, target_naics)

    technical = score_technical(
        description,
        keyword_groups
    )

    evidence = score_description_evidence(
        description
    )

    stage = score_procurement_stage(row)

    total = (
        naics["score"] +
        technical["score"] +
        evidence["score"] +
        stage["score"]
    )

    total = min(100, total)

    # Title matches are useful for discovery but do not count
    # as technical evidence.
    title_matches = sorted({
        keyword
        for keywords in keyword_groups.values()
        for keyword in keywords
        if contains_phrase(title.lower(), keyword)
    })

    # A Strong Fit requires multiple independent signals.
    strong_fit_conditions = (
        total >= STRONG_FIT_THRESHOLD
        and naics["matched"]
        and len(technical["matched_groups"]) >= 2
        and bool(description)
        and bool(technical["matched_keywords"])
        and evidence["score"] >= 15
    )

    if not description:
        category = "Insufficient Evidence"

    elif strong_fit_conditions:
        category = "Strong Fit"

    elif total >= POSSIBLE_FIT_THRESHOLD:
        category = "Possible Fit"

    elif total >= WEAK_FIT_THRESHOLD:
        category = "Weak Fit"

    else:
        category = "Insufficient Evidence"

    special_requirements = identify_special_requirements(
        full_text
    )

    pursuit_status = determine_pursuit_status(row)

    priority = clean(row.get("priority_level")).upper()

    # -----------------------------------------------------
    # Recommended action
    # -----------------------------------------------------

    if pursuit_status == "Research Only - Award Notice":
        action = "Research Only - Award Notice"

    elif pursuit_status == "Noncompetitive / Not an Open Bid":
        action = "Do Not Treat as Competitive Bid"

    elif category == "Strong Fit" and priority == "P1":
        action = "Immediate Technical and Deadline Review"

    elif category == "Strong Fit":
        action = "Prioritize for Detailed Solicitation Review"

    elif category == "Possible Fit" and priority == "P1":
        action = "Urgent Review - Confirm Technical Alignment"

    elif category == "Possible Fit":
        action = "Review Statement of Work and Requirements"

    elif category == "Weak Fit":
        action = "Low Priority - Validate Scope or Teaming Potential"

    else:
        action = "Manual Review - Obtain Additional Evidence"

    # Specialized requirements always need verification.
    if special_requirements:
        action += " - Verify Specialized Requirements"

    reasons = []

    if naics["matched"]:
        reasons.append("Exact target NAICS alignment")
    else:
        reasons.append("No exact target NAICS match")

    if technical["matched_groups"]:
        reasons.append(
            "Technical groups: "
            + ", ".join(technical["matched_groups"])
        )
    else:
        reasons.append(
            "No configured technical groups found in description"
        )

    reasons.append(
        f"Description evidence: {evidence['status']}"
    )

    reasons.append(
        f"Procurement stage: {stage['stage']}"
    )

    if special_requirements:
        reasons.append(
            "Special requirements need verification: "
            + ", ".join(special_requirements)
        )

    if title_matches:
        reasons.append(
            "Title-only keywords: "
            + ", ".join(title_matches)
        )

    return {
        "relevance_v2_score": total,
        "relevance_v2_maximum_score": 100,
        "relevance_v2_category": category,

        "v2_naics_score": naics["score"],
        "v2_naics_match": (
            "Yes" if naics["matched"] else "No"
        ),

        "v2_technical_score": technical["score"],
        "v2_technical_matched_groups": "; ".join(
            technical["matched_groups"]
        ),
        "v2_technical_matched_keywords": "; ".join(
            technical["matched_keywords"]
        ),

        "v2_description_evidence_score": evidence["score"],
        "v2_description_evidence_status": evidence["status"],
        "v2_scope_evidence": "; ".join(
            evidence["scope_matches"]
        ),
        "v2_requirement_evidence": "; ".join(
            evidence["requirement_matches"]
        ),

        "v2_procurement_stage_score": stage["score"],
        "v2_procurement_stage": stage["stage"],

        "v2_title_only_keywords": "; ".join(title_matches),

        "v2_special_requirements": "; ".join(
            special_requirements
        ),
        "v2_special_requirements_review": (
            "Yes" if special_requirements else "No"
        ),

        "v2_pursuit_status": pursuit_status,
        "v2_recommended_action": action,
        "v2_reason": "; ".join(reasons),

        "v2_manual_review_required": (
            "Yes"
            if (
                category != "Strong Fit"
                or special_requirements
                or pursuit_status != "Review Official Notice"
            )
            else "No"
        ),
    }


# ---------------------------------------------------------
# 8. MAIN
# ---------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description=(
            "TTE Opportunity Relevance Engine V2 - "
            "CSV-only assessment."
        )
    )

    parser.add_argument(
        "--input",
        type=str,
        help="Optional prioritization CSV path."
    )

    args = parser.parse_args()

    input_file = (
        Path(args.input).resolve()
        if args.input
        else find_latest_input()
    )

    if not input_file.exists():
        raise FileNotFoundError(
            f"Input CSV not found: {input_file}"
        )

    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    keyword_groups = {
        str(group): flatten_keywords(keywords)
        for group, keywords in KEYWORD_GROUPS.items()
    }

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    output_file = REPORT_DIR / (
        f"sam_opportunity_relevance_v2_{timestamp}.csv"
    )

    with input_file.open(
        "r",
        encoding="utf-8-sig",
        newline=""
    ) as source:

        reader = csv.DictReader(source)

        if not reader.fieldnames:
            raise ValueError(
                "The input CSV has no column headers."
            )

        original_fields = reader.fieldnames
        rows = list(reader)

    results = []

    for row in rows:
        try:
            assessment = assess_opportunity(
                row,
                keyword_groups,
                TARGET_NAICS
            )

            results.append({
                **row,
                **assessment,
            })

        except Exception as exc:
            results.append({
                **row,
                "relevance_v2_score": 0,
                "relevance_v2_maximum_score": 100,
                "relevance_v2_category": "Assessment Error",
                "v2_reason": str(exc),
                "v2_recommended_action": "Manual Review",
                "v2_manual_review_required": "Yes",
            })

    new_fields = [
        "relevance_v2_score",
        "relevance_v2_maximum_score",
        "relevance_v2_category",
        "v2_naics_score",
        "v2_naics_match",
        "v2_technical_score",
        "v2_technical_matched_groups",
        "v2_technical_matched_keywords",
        "v2_description_evidence_score",
        "v2_description_evidence_status",
        "v2_scope_evidence",
        "v2_requirement_evidence",
        "v2_procurement_stage_score",
        "v2_procurement_stage",
        "v2_title_only_keywords",
        "v2_special_requirements",
        "v2_special_requirements_review",
        "v2_pursuit_status",
        "v2_recommended_action",
        "v2_reason",
        "v2_manual_review_required",
    ]

    output_fields = list(original_fields)

    for field in new_fields:
        if field not in output_fields:
            output_fields.append(field)

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
        writer.writerows(results)

    # -----------------------------------------------------
    # SUMMARY
    # -----------------------------------------------------

    categories = {}

    for row in results:
        category = row.get(
            "relevance_v2_category",
            "Unknown"
        )

        categories[category] = (
            categories.get(category, 0) + 1
        )

    average_score = (
        sum(
            int(row.get("relevance_v2_score", 0) or 0)
            for row in results
        ) / len(results)
        if results else 0
    )

    print("\n" + "=" * 65)
    print("TTE OPPORTUNITY RELEVANCE ENGINE V2")
    print("=" * 65)

    print(f"Input file: {input_file.name}")
    print(f"Total opportunities: {len(results)}")
    print(f"Average relevance score: {average_score:.2f}/100")

    print("\nRELEVANCE CLASSIFICATION")
    print("-" * 45)

    for category, count in sorted(categories.items()):
        print(f"{category}: {count}")

    print("\nOUTPUT FILE")
    print("-" * 45)
    print(output_file)

    print("\nSCORING MODEL")
    print("-" * 45)
    print("NAICS alignment: 25 points")
    print("Technical capability: 35 points")
    print("Description evidence: 30 points")
    print("Procurement stage: 10 points")

    print("\nSAFETY CHECKS")
    print("-" * 45)
    print("NAICS-only Strong Fit: Not permitted")
    print("Title-only technical evidence: Not counted")
    print("Missing descriptions: Flagged")
    print("Specialized requirements: Flagged for review")
    print("PostgreSQL accessed: NO")
    print("Existing reports modified: NO")
    print("V1 relevance engine modified: NO")
    print("Qualification scores modified: NO")
    print("Prioritization scores modified: NO")

    print("\nV2 assessment completed.")


if __name__ == "__main__":
    main()
