"""
GovCon BD Intelligence & Automation Platform
Target NAICS Opportunity Qualification

Reads:
    data/reports/target_naics_discovery.csv

Writes:
    data/reports/qualified_opportunities_run2.csv

Uses the existing capability matcher.
Does not modify PostgreSQL or the SAM.gov importer.
"""

from __future__ import annotations

import csv
import re
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.capability_matcher import match_capabilities  # noqa: E402


INPUT_FILE = (
    PROJECT_ROOT / "data" / "reports" / "target_naics_discovery.csv"
)

OUTPUT_FILE = (
    PROJECT_ROOT / "data" / "reports" / "qualified_opportunities_run2.csv"
)


# ============================================================
# CONFIGURATION
# ============================================================

MARKET_RESEARCH_TYPES = {
    "sources sought",
    "request for information",
    "rfi",
}

HISTORICAL_NOTICE_TYPES = {
    "award notice",
    "award",
    "justification",
    "justification and approval",
}

RELEVANCE_KEYWORDS = {
    "engineering": [
        "engineering services",
        "systems engineering",
        "engineering support",
        "technical services",
        "technical support",
    ],
    "supply_chain": [
        "supply chain",
        "supplier management",
        "supplier performance",
        "supplier oversight",
        "supplier quality",
        "vendor management",
    ],
    "logistics": [
        "logistics support",
        "logistics management",
        "material management",
        "inventory management",
        "distribution support",
    ],
    "procurement": [
        "procurement support",
        "acquisition support",
        "contract administration",
        "post-award support",
        "purchasing support",
    ],
    "analytics": [
        "data analysis",
        "performance metrics",
        "risk assessment",
        "process improvement",
        "continuous improvement",
        "analytics",
    ],
    "program_support": [
        "program management support",
        "project management support",
        "management support services",
        "program support",
    ],
}

PRODUCT_INDICATORS = [
    "replacement parts",
    "spare parts",
    "parts kit",
    "equipment purchase",
    "hardware supplies",
    "bulk purchase",
    "commodity purchase",
    "medical supplies",
    "office furniture",
    "vehicle parts",
    "aircraft parts",
    "ship parts",
    "ammunition",
    "pharmaceuticals",
]

# Screening threshold only. This is not proof of eligibility.
MIN_TECHNICAL_SCORE = 20


# ============================================================
# GENERAL HELPERS
# ============================================================

def text(value: Any) -> str:
    """Convert CSV/API values into readable text."""

    if value is None:
        return ""

    if isinstance(value, dict):
        return "; ".join(
            f"{key}: {text(item)}"
            for key, item in value.items()
            if item is not None
        )

    if isinstance(value, (list, tuple, set)):
        return "; ".join(text(item) for item in value)

    return str(value).strip()


def normalize(value: Any) -> str:
    """Normalize text for matching."""

    return re.sub(r"\s+", " ", text(value).lower()).strip()


def first_value(
    row: dict[str, Any],
    *field_names: str,
) -> str:
    """Return the first nonempty field."""

    for field_name in field_names:
        value = text(row.get(field_name))

        if value:
            return value

    return ""


def parse_date(value: Any) -> date | None:
    """Parse common SAM.gov date formats."""

    value_text = text(value)

    if not value_text:
        return None

    try:
        return datetime.fromisoformat(
            value_text.replace("Z", "+00:00")
        ).date()
    except ValueError:
        pass

    formats = [
        "%Y-%m-%d",
        "%m/%d/%Y",
        "%m-%d-%Y",
        "%Y/%m/%d",
        "%Y-%m-%d %H:%M:%S",
        "%m/%d/%Y %H:%M",
    ]

    for fmt in formats:
        try:
            return datetime.strptime(value_text, fmt).date()
        except ValueError:
            continue

    return None


def integer(value: Any, default: int = 0) -> int:
    """Safely convert a value to an integer."""

    try:
        return int(float(text(value)))
    except (ValueError, TypeError):
        return default


def bool_value(value: Any) -> bool:
    """Interpret common boolean values."""

    if isinstance(value, bool):
        return value

    if isinstance(value, (int, float)):
        return value != 0

    return normalize(value) in {
        "true",
        "yes",
        "1",
        "match",
        "matched",
    }


def printable(value: Any) -> str:
    """Format values for CSV output."""

    return text(value)


# ============================================================
# NOTICE CLASSIFICATION
# ============================================================

def classify_notice(notice_type: str) -> str:
    """Classify notices for preliminary BD screening."""

    notice = normalize(notice_type)

    if not notice:
        return "Unknown"

    if any(
        term in notice
        for term in HISTORICAL_NOTICE_TYPES
    ):
        return "Historical / Award"

    if any(
        term in notice
        for term in MARKET_RESEARCH_TYPES
    ):
        return "Market Research"

    if "special notice" in notice:
        return "Special Notice / Review"

    if (
        "presolicitation" in notice
        or "pre-solicitation" in notice
    ):
        return "Pre-Solicitation"

    if "solicitation" in notice:
        return "Active Procurement"

    return "Other / Review"


# ============================================================
# DEADLINE ANALYSIS
# ============================================================

def deadline_status(
    deadline_value: str,
    today: date,
) -> tuple[str, int | None]:
    """Calculate deadline status and days remaining."""

    deadline = parse_date(deadline_value)

    if deadline is None:
        return "Unknown", None

    days = (deadline - today).days

    if days < 0:
        return "Expired", days

    if days == 0:
        return "Due Today", 0

    if days <= 7:
        return "Due Within 7 Days", days

    if days <= 30:
        return "Due Within 30 Days", days

    return "More Than 30 Days", days


# ============================================================
# PRELIMINARY SCOPE SCREEN
# ============================================================

def screen_scope(
    title: str,
    description: str,
    naics_code: str,
) -> tuple[str, list[str], list[str]]:
    """Identify possible service relevance and product signals."""

    searchable_text = normalize(
        f"{title} {description} {naics_code}"
    )

    matched_groups = []

    for group_name, phrases in RELEVANCE_KEYWORDS.items():
        if any(
            normalize(phrase) in searchable_text
            for phrase in phrases
        ):
            matched_groups.append(group_name)

    matched_products = [
        phrase
        for phrase in PRODUCT_INDICATORS
        if normalize(phrase) in searchable_text
    ]

    if matched_groups and matched_products:
        status = "Mixed Signals - Review"

    elif matched_groups:
        status = "Potentially Relevant"

    elif matched_products:
        status = "Possible Product Purchase"

    else:
        status = "Needs Manual Review"

    return status, matched_groups, matched_products


# ============================================================
# CAPABILITY MATCHER INTEGRATION
# ============================================================

def run_matcher(
    row: dict[str, Any],
) -> dict[str, Any]:
    """Prepare a discovery record for the existing matcher."""

    opportunity = {
        "title": first_value(
            row,
            "title",
            "opportunity_title",
        ),
        "description": first_value(
            row,
            "description",
        ),
        "naics_code": first_value(
            row,
            "naics_code",
            "naics",
        ),
        "agency_name": first_value(
            row,
            "agency",
            "agency_name",
        ),
        "opportunity_type": first_value(
            row,
            "notice_type",
            "opportunity_type",
        ),
        "solicitation_number": first_value(
            row,
            "solicitation_number",
        ),
        "place_of_performance": first_value(
            row,
            "place_of_performance",
        ),
    }

    result = match_capabilities(opportunity)

    if not isinstance(result, dict):
        raise TypeError(
            "match_capabilities() did not return a dictionary"
        )

    return result


# ============================================================
# QUALIFY ONE OPPORTUNITY
# ============================================================

def qualify(
    row: dict[str, Any],
    today: date,
) -> dict[str, Any]:
    """Enrich one opportunity with qualification results."""

    title = first_value(
        row,
        "title",
        "opportunity_title",
    )

    description = first_value(
        row,
        "description",
    )

    naics = first_value(
        row,
        "naics_code",
        "naics",
    )

    notice_type = first_value(
        row,
        "notice_type",
        "opportunity_type",
    )

    deadline = first_value(
        row,
        "response_deadline",
    )

    agency = first_value(
        row,
        "agency",
        "agency_name",
    )

    notice_category = classify_notice(notice_type)

    deadline_category, days_remaining = deadline_status(
        deadline,
        today,
    )

    scope_category, scope_groups, product_indicators = screen_scope(
        title,
        description,
        naics,
    )

    match_result: dict[str, Any] = {}
    match_error = ""

    try:
        match_result = run_matcher(row)

    except Exception as exc:
        match_error = f"{type(exc).__name__}: {exc}"

    # IMPORTANT:
    # These are the actual result keys from the existing matcher.

    technical_score = integer(
        match_result.get("technical_score"),
        0,
    )

    naics_match = bool_value(
        match_result.get("target_naics_match", False)
    )

    capability_fit_score = match_result.get(
        "capability_fit_score",
        "",
    )

    fit_label = text(
        match_result.get("fit_label", "")
    )

    matcher_groups = printable(
        match_result.get("matched_keyword_groups", [])
    )

    matcher_terms = printable(
        match_result.get("matched_terms", [])
    )

    core_competencies = printable(
        match_result.get("matched_core_competencies", [])
    )

    review_flags = printable(
        match_result.get("review_flags", [])
    )

    # --------------------------------------------------------
    # Preliminary qualification decision
    # --------------------------------------------------------

    reasons: list[str] = []

    if match_error:
        decision = "Manual Review"
        reasons.append("Capability matcher failed")

    elif notice_category == "Historical / Award":
        decision = "Research Only"
        reasons.append(
            "Historical or award-related notice; not treated as an open bid"
        )

    elif deadline_category == "Expired":
        decision = "Expired - Review"
        reasons.append(
            "Response deadline has passed; verify the official notice"
        )

    elif notice_category == "Market Research":
        decision = "Market Research"
        reasons.append(
            "Potential early-stage procurement intelligence"
        )

    elif notice_category == "Special Notice / Review":
        decision = "Manual Review"
        reasons.append(
            "Special notice requires inspection"
        )

    elif notice_category == "Pre-Solicitation":
        decision = "Monitor - Pre-Solicitation"
        reasons.append(
            "Monitor for a future solicitation"
        )

    elif notice_category == "Active Procurement":

        if scope_category == "Possible Product Purchase":
            decision = "Low Priority - Review"
            reasons.append(
                "Product-purchase indicators found; inspect the actual scope"
            )

        elif naics_match and (
            technical_score >= MIN_TECHNICAL_SCORE
            or scope_category in {
                "Potentially Relevant",
                "Mixed Signals - Review",
            }
        ):
            decision = "Potential Bid Candidate"
            reasons.append(
                "Target NAICS and preliminary service/capability signals found"
            )

        elif not naics_match and (
            technical_score >= MIN_TECHNICAL_SCORE
            or scope_category in {
                "Potentially Relevant",
                "Mixed Signals - Review",
            }
        ):
            decision = "Manual Review"
            reasons.append(
                "Scope or technical signals found, but target NAICS match "
                "is unconfirmed"
            )

        else:
            decision = "Manual Review"
            reasons.append(
                "Insufficient evidence for preliminary qualification"
            )

    else:
        decision = "Manual Review"
        reasons.append(
            "Notice category requires manual review"
        )

    if not deadline:
        reasons.append("Response deadline not provided")

    if not description:
        reasons.append("Description is missing")

    if not first_value(row, "source_url", "url"):
        reasons.append("Source URL is missing")

    if product_indicators:
        reasons.append(
            "Product indicators: "
            + ", ".join(product_indicators)
        )

    if scope_groups:
        reasons.append(
            "Relevant keyword groups: "
            + ", ".join(scope_groups)
        )

    if review_flags:
        reasons.append(
            "Matcher review flags: "
            + review_flags
        )

    # --------------------------------------------------------
    # Preliminary priority score
    # --------------------------------------------------------

    # This score is a ranking aid, not a probability of winning.

    priority = 0

    if notice_category == "Active Procurement":
        priority += 30

    elif notice_category == "Pre-Solicitation":
        priority += 20

    elif notice_category == "Market Research":
        priority += 10

    if naics_match:
        priority += 20

    priority += min(max(technical_score, 0), 100) // 5

    if scope_category == "Potentially Relevant":
        priority += 15

    elif scope_category == "Mixed Signals - Review":
        priority += 5

    if deadline_category == "Due Within 7 Days":
        priority += 10

    elif deadline_category == "Due Within 30 Days":
        priority += 7

    elif deadline_category == "More Than 30 Days":
        priority += 3

    if deadline_category == "Expired":
        priority = max(0, priority - 30)

    if notice_category == "Historical / Award":
        priority = 0

    if match_error:
        priority = 0

    priority = min(max(priority, 0), 100)

    # Preserve all original discovery CSV fields.

    output = dict(row)

    output.update({
        "agency_normalized": agency,
        "notice_category": notice_category,
        "deadline_status": deadline_category,
        "days_until_deadline": (
            days_remaining
            if days_remaining is not None
            else ""
        ),
        "scope_screen": scope_category,
        "scope_matched_groups": "; ".join(scope_groups),
        "product_indicators": "; ".join(product_indicators),

        # Correct matcher output fields:
        "capability_fit_score": capability_fit_score,
        "capability_fit_label": fit_label,
        "naics_match": naics_match,
        "technical_score": technical_score,
        "matcher_matched_groups": matcher_groups,
        "matcher_matched_terms": matcher_terms,
        "matcher_core_competencies": core_competencies,
        "matcher_review_flags": review_flags,

        "matcher_error": match_error,
        "qualification_decision": decision,
        "priority_score": priority,
        "qualification_reasons": "; ".join(reasons),
        "qualification_checked_date": today.isoformat(),
    })

    return output


# ============================================================
# MAIN PROGRAM
# ============================================================

def main() -> int:
    """Read discovery CSV and create the qualification report."""

    print("=" * 68)
    print("GOVCON BD INTELLIGENCE PLATFORM")
    print("Target NAICS Opportunity Qualification")
    print("=" * 68)

    print(f"Project root : {PROJECT_ROOT}")
    print(f"Input file   : {INPUT_FILE}")
    print(f"Output file  : {OUTPUT_FILE}")
    print()

    if not INPUT_FILE.exists():
        print("ERROR: Discovery report not found.")
        print(f"Expected file: {INPUT_FILE}")
        print(
            "Run scripts\\discover_target_naics_opportunities.py first."
        )
        return 1

    try:
        with INPUT_FILE.open(
            "r",
            encoding="utf-8-sig",
            newline="",
        ) as csv_file:

            reader = csv.DictReader(csv_file)

            if not reader.fieldnames:
                print("ERROR: Input CSV has no column headers.")
                return 1

            rows = list(reader)

    except (OSError, csv.Error) as exc:
        print(f"ERROR: Could not read discovery CSV: {exc}")
        return 1

    if not rows:
        print("No discovery records were found.")
        return 0

    print(f"Records loaded: {len(rows)}")
    print("Qualifying opportunities...")
    print()

    today = date.today()

    output_rows: list[dict[str, Any]] = []
    failed_records = 0

    for index, row in enumerate(rows, start=1):

        try:
            result = qualify(row, today)
            output_rows.append(result)

            if result.get("matcher_error"):
                failed_records += 1

        except Exception as exc:
            failed_records += 1

            print(
                f"WARNING: Record {index} failed: "
                f"{type(exc).__name__}: {exc}"
            )

        if index % 50 == 0 or index == len(rows):
            print(
                f"Processed {index} of {len(rows)} records"
            )

    if not output_rows:
        print("ERROR: No records were successfully processed.")
        return 1

    # Sort by preliminary priority and then technical score.

    output_rows.sort(
        key=lambda item: (
            integer(item.get("priority_score")),
            integer(item.get("technical_score")),
        ),
        reverse=True,
    )

    # Include all source fields and all new qualification fields.

    columns: list[str] = []

    for row in output_rows:
        for key in row:
            if key not in columns:
                columns.append(key)

    try:
        OUTPUT_FILE.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        with OUTPUT_FILE.open(
            "w",
            encoding="utf-8-sig",
            newline="",
        ) as csv_file:

            writer = csv.DictWriter(
                csv_file,
                fieldnames=columns,
                extrasaction="ignore",
            )

            writer.writeheader()
            writer.writerows(output_rows)

    except (OSError, csv.Error) as exc:
        print(f"ERROR: Could not write output CSV: {exc}")
        return 1

    # --------------------------------------------------------
    # Summary
    # --------------------------------------------------------

    print()
    print("=" * 68)
    print("QUALIFICATION SUMMARY")
    print("=" * 68)

    print(f"Input records       : {len(rows)}")
    print(f"Output records      : {len(output_rows)}")
    print(f"Matcher failures    : {failed_records}")
    print(f"Report              : {OUTPUT_FILE}")
    print()

    for field, heading in [
        ("qualification_decision", "Qualification decisions"),
        ("notice_category", "Notice categories"),
        ("deadline_status", "Deadline statuses"),
        ("naics_code", "NAICS distribution"),
    ]:

        print(f"{heading}:")

        counts: dict[str, int] = {}

        for row in output_rows:
            value = text(row.get(field)) or "Unknown"
            counts[value] = counts.get(value, 0) + 1

        for label, count in sorted(
            counts.items(),
            key=lambda item: item[1],
            reverse=True,
        ):
            print(f"  {label}: {count}")

        print()

    print("Top 10 opportunities by preliminary priority:")
    print("-" * 68)

    for index, row in enumerate(output_rows[:10], start=1):

        title = first_value(
            row,
            "title",
            "opportunity_title",
        )

        print(f"{index}. {title[:110]}")

        print(
            f"   NAICS: {first_value(row, 'naics_code', 'naics')}"
            f" | NAICS match: {row.get('naics_match')}"
            f" | Fit: {row.get('capability_fit_score', '')}"
            f" | Priority: {row.get('priority_score', 0)}"
        )

        print(
            f"   Decision: "
            f"{row.get('qualification_decision', '')}"
        )

        print(
            f"   Deadline: "
            f"{first_value(row, 'response_deadline') or 'Unknown'}"
        )

        print()

    print("=" * 68)
    print("SUCCESS: Qualification report generated.")
    print("PostgreSQL was not modified.")
    print("=" * 68)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
