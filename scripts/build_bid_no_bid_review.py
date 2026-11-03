"""
GovCon BD Intelligence Platform
Bid/No-Bid Review Module

Input:
    data/reports/qualified_opportunities_run2.csv

Output:
    data/reports/bid_no_bid_review.csv

This script:
    1. Reads the existing qualification report.
    2. Evaluates deadlines and qualification decisions.
    3. Identifies contract-vehicle and eligibility checks.
    4. Creates recommended next actions.
    5. Preserves the original input file.
    6. Does not modify PostgreSQL or call the SAM.gov API.

IMPORTANT:
Recommendations are preliminary screening results.
A human must review the solicitation before making a final bid decision.
"""

import csv
import sys
from datetime import datetime, timezone
from pathlib import Path


# ---------------------------------------------------------
# PROJECT PATHS
# ---------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent

INPUT_FILE = (
    PROJECT_ROOT
    / "data"
    / "reports"
    / "qualified_opportunities_run2.csv"
)

OUTPUT_FILE = (
    PROJECT_ROOT
    / "data"
    / "reports"
    / "bid_no_bid_review.csv"
)


# ---------------------------------------------------------
# HELPER FUNCTIONS
# ---------------------------------------------------------

def clean(value):
    """Convert a value to a clean string."""
    if value is None:
        return ""
    return str(value).strip()


def parse_number(value):
    """Convert a CSV value to a float, if possible."""
    value = clean(value)

    if not value:
        return None

    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def parse_datetime(value):
    """
    Parse an ISO date or datetime.

    Examples:
        2026-11-02
        2026-11-02T11:00:00+01:00
        2026-11-02T11:00:00-05:00

    Timezone-aware deadlines are converted to UTC.
    Date-only values are interpreted as dates, not exact deadlines.
    """
    value = clean(value)

    if not value:
        return None

    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))

        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)

        return parsed.astimezone(timezone.utc)

    except ValueError:
        return None


def parse_date_only(value):
    """Parse a YYYY-MM-DD date."""
    value = clean(value)

    if not value:
        return None

    try:
        return datetime.strptime(value[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def split_flags(*values):
    """Collect distinct flags from semicolon-separated CSV fields."""
    flags = []

    for value in values:
        for item in clean(value).split(";"):
            item = item.strip()

            if item and item.lower() not in {
                "none",
                "nan",
                "n/a",
            }:
                if item not in flags:
                    flags.append(item)

    return flags


def format_flags(flags):
    """Format a list of flags for CSV output."""
    return "; ".join(flags) if flags else "None identified"


def get_deadline_status(row, now_utc):
    """
    Determine deadline status.

    An exact timestamp is compared using its timezone.
    A date-only deadline is treated as an unconfirmed date,
    because the exact closing time is unknown.
    """
    deadline_text = clean(row.get("response_deadline"))

    if not deadline_text:
        return "Unknown Deadline", None, None

    deadline_dt = parse_datetime(deadline_text)

    if deadline_dt is not None:
        remaining_seconds = (
            deadline_dt - now_utc
        ).total_seconds()

        remaining_days = int(
            remaining_seconds // 86400
        )

        if remaining_seconds < 0:
            return "Past Deadline - Verify Status", remaining_days, deadline_dt

        if remaining_seconds <= 86400:
            return "Due Within 24 Hours", remaining_days, deadline_dt

        if remaining_seconds <= 7 * 86400:
            return "Due Within 7 Days", remaining_days, deadline_dt

        if remaining_seconds <= 30 * 86400:
            return "Due Within 30 Days", remaining_days, deadline_dt

        return "More Than 30 Days", remaining_days, deadline_dt

    date_value = parse_date_only(deadline_text)

    if date_value is not None:
        today = now_utc.date()

        if date_value < today:
            return "Past Date - Verify Exact Deadline", None, None

        if date_value == today:
            return "Due Date Today - Verify Closing Time", 0, None

        days_remaining = (date_value - today).days

        if days_remaining <= 7:
            return "Due Within 7 Days - Time Unknown", days_remaining, None

        if days_remaining <= 30:
            return "Due Within 30 Days - Time Unknown", days_remaining, None

        return "More Than 30 Days - Time Unknown", days_remaining, None

    return "Invalid Deadline - Verify", None, None


def determine_eligibility_gate(row):
    """
    Identify eligibility questions from available opportunity text.

    These are screening flags, not definitive eligibility decisions.
    """
    text = " ".join(
        [
            clean(row.get("title")),
            clean(row.get("description")),
            clean(row.get("qualification_reasons")),
            clean(row.get("set_aside")),
        ]
    ).lower()

    gates = []

    if "seaport nxg" in text or "seaport" in text:
        gates.append(
            "Verify SeaPort NxG contract-holder eligibility; "
            "consider teaming if the company cannot compete directly"
        )

    if (
        "teps iii" in text
        or "technical, engineering, and programmatic support services iii"
        in text
    ):
        gates.append(
            "Verify TEPS III BPA access and eligibility to compete"
        )

    if any(
        term in text
        for term in [
            "small business set-aside",
            "small business set aside",
            "sdvosb",
            "service-disabled veteran-owned",
            "8(a)",
            "hubzone",
            "women-owned small business",
            "wosb",
        ]
    ):
        gates.append(
            "Verify the solicitation's set-aside rules and "
            "the company's current eligibility/certification"
        )

    if "no set aside used" in text or "no set-aside" in text:
        gates.append(
            "Confirm the recorded set-aside field against the current solicitation"
        )

    if not gates:
        gates.append(
            "Verify offeror eligibility, mandatory qualifications, "
            "and any required contract vehicle"
        )

    return gates


def determine_recommended_action(row, deadline_status):
    """Generate a conservative preliminary recommendation."""
    decision = clean(row.get("qualification_decision"))
    category = clean(row.get("notice_category")).lower()
    notice_type = clean(row.get("notice_type")).lower()

    if not decision:
        return (
            "Needs Data Correction",
            "The qualification decision is blank; correct or review "
            "the source qualification record before routing this opportunity.",
        )

    if "historical" in category or "award" in category:
        return (
            "Research Only",
            "This appears to be a historical or award-related notice. "
            "Use it for market intelligence unless the current notice "
            "confirms an active procurement.",
        )

    if "expired" in decision.lower():
        return (
            "Verify Status - Possible No-Bid",
            "Verify the current SAM.gov notice and whether an amendment "
            "changed the deadline before excluding the opportunity.",
        )

    if deadline_status.startswith("Past Deadline"):
        return (
            "Urgent Status Verification",
            "The recorded deadline has passed. Check SAM.gov for amendments, "
            "reopening, cancellation, or a corrected deadline before proceeding.",
        )

    if deadline_status.startswith("Past Date"):
        return (
            "Verify Exact Deadline",
            "The recorded deadline date has passed, but the source value "
            "does not provide a usable exact timestamp. Verify the current notice.",
        )

    if "research only" in decision.lower():
        return (
            "Research Only",
            "Retain for agency, competitor, or market research. "
            "Do not treat this as an active bid recommendation.",
        )

    if "market research" in decision.lower():
        return (
            "Market Research",
            "Review the notice for agency needs, upcoming requirements, "
            "and potential teaming or customer-engagement opportunities.",
        )

    if "monitor" in decision.lower() or "pre-solicitation" in category:
        return (
            "Monitor",
            "Track amendments and the expected solicitation. "
            "Prepare questions and review likely requirements when available.",
        )

    if "manual review" in decision.lower():
        return (
            "Manual Bid Review",
            "Review the complete solicitation, scope, eligibility, deadline, "
            "and required qualifications before deciding whether to bid.",
        )

    if "no-bid" in decision.lower() or "no bid" in decision.lower():
        return (
            "No-Bid Review",
            "Validate the recorded no-bid rationale and document "
            "the final decision with the responsible reviewer.",
        )

    if "potential bid candidate" in decision.lower():
        if "solicitation" not in notice_type:
            return (
                "Review Notice Type",
                "The opportunity passed preliminary qualification, but its "
                "notice type must be checked before treating it as a bid.",
            )

        if deadline_status in {
            "Due Within 24 Hours",
            "Due Within 7 Days",
        }:
            return (
                "Urgent Bid/No-Bid Review",
                "Review the full solicitation immediately. Confirm eligibility, "
                "submission instructions, required documents, and exact closing time.",
            )

        return (
            "Bid/No-Bid Review",
            "Review the full solicitation, eligibility, technical scope, "
            "contract vehicle, resources, pricing, and submission requirements.",
        )

    if "low priority" in decision.lower():
        return (
            "Low Priority Review",
            "Retain only if additional scope or agency information "
            "shows a stronger fit.",
        )

    return (
        "Manual Review",
        "Review the original notice and qualification rationale "
        "before assigning a final disposition.",
    )


def determine_scope_alignment(row):
    """Summarize the existing preliminary scope screen."""
    scope_screen = clean(row.get("scope_screen"))
    matched_groups = clean(row.get("scope_matched_groups"))
    matcher_groups = clean(row.get("matcher_matched_groups"))
    core_competencies = clean(row.get("matcher_core_competencies"))

    details = []

    if scope_screen:
        details.append(f"Scope screen: {scope_screen}")

    if matched_groups:
        details.append(f"Scope groups: {matched_groups}")

    if matcher_groups:
        details.append(f"Matcher groups: {matcher_groups}")

    if core_competencies:
        details.append(f"Competencies: {core_competencies}")

    return " | ".join(details) if details else "No scope evidence recorded"


def determine_risk_flags(row, deadline_status, eligibility_gates):
    """Collect risks and checks that need human attention."""
    flags = []

    if not clean(row.get("qualification_decision")):
        flags.append("Missing qualification decision")

    if clean(row.get("matcher_error")):
        flags.append("Capability matcher error recorded")

    if clean(row.get("naics_match")).lower() not in {"true", "1", "yes"}:
        flags.append("Target NAICS match not confirmed")

    if deadline_status in {
        "Past Deadline - Verify Status",
        "Past Date - Verify Exact Deadline",
        "Invalid Deadline - Verify",
    }:
        flags.append("Deadline requires urgent verification")

    if deadline_status == "Unknown Deadline":
        flags.append("No response deadline recorded")

    if deadline_status in {
        "Due Within 24 Hours",
        "Due Within 7 Days",
        "Due Within 7 Days - Time Unknown",
        "Due Within 30 Days - Time Unknown",
    }:
        flags.append("Short deadline or closing time requires verification")

    if clean(row.get("matcher_review_flags")):
        flags.extend(
            split_flags(row.get("matcher_review_flags"))
        )

    if clean(row.get("product_indicators")):
        flags.append(
            "Product indicators present; verify whether requirement "
            "matches company service capabilities"
        )

    flags.extend(eligibility_gates)

    return list(dict.fromkeys(flags))


# ---------------------------------------------------------
# MAIN REVIEW PROCESS
# ---------------------------------------------------------

def main():
    print("=" * 72)
    print("GOVCON BD INTELLIGENCE PLATFORM")
    print("BID/NO-BID REVIEW MODULE")
    print("=" * 72)

    if not INPUT_FILE.exists():
        print(f"ERROR: Input report not found:\n{INPUT_FILE}")
        print(
            "\nCreate the qualification report first, then run this script again."
        )
        return 1

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    # Capture one consistent timestamp for this report run.
    now_utc = datetime.now(timezone.utc)

    try:
        with INPUT_FILE.open(
            "r",
            encoding="utf-8-sig",
            newline="",
        ) as source_file:
            reader = csv.DictReader(source_file)

            if not reader.fieldnames:
                print("ERROR: Input CSV has no column headers.")
                return 1

            rows = list(reader)
            input_fields = set(reader.fieldnames)

    except (OSError, csv.Error) as exc:
        print(f"ERROR: Could not read input report: {exc}")
        return 1

    if not rows:
        print("ERROR: Input report contains no data rows.")
        return 1

    required_fields = {
        "notice_id",
        "title",
        "notice_type",
        "notice_category",
        "qualification_decision",
        "response_deadline",
        "source_url",
    }

    missing_fields = sorted(required_fields - input_fields)

    if missing_fields:
        print("ERROR: Required fields are missing from the input CSV:")
        for field in missing_fields:
            print(f"  - {field}")

        print(
            "\nNo output was generated. Check the input schema "
            "before changing this script."
        )
        return 1

    output_fields = [
        "review_id",
        "notice_id",
        "solicitation_number",
        "title",
        "agency",
        "notice_type",
        "notice_category",
        "naics_code",
        "set_aside",
        "posted_date",
        "response_deadline",
        "deadline_status",
        "days_until_deadline",
        "qualification_decision",
        "priority_score",
        "capability_fit_score",
        "technical_score",
        "naics_match",
        "scope_alignment",
        "eligibility_gate",
        "recommended_action",
        "risk_flags",
        "required_checks",
        "review_status",
        "source_url",
        "review_generated_utc",
    ]

    output_rows = []
    action_counts = {}
    deadline_counts = {}
    missing_decision_count = 0

    for row in rows:
        notice_id = clean(row.get("notice_id"))
        title = clean(row.get("title"))

        deadline_status, days_until_deadline, _ = get_deadline_status(
            row,
            now_utc,
        )

        eligibility_gates = determine_eligibility_gate(row)

        recommended_action, action_reason = determine_recommended_action(
            row,
            deadline_status,
        )

        risk_flags = determine_risk_flags(
            row,
            deadline_status,
            eligibility_gates,
        )

        required_checks = [
            "Open the original SAM.gov notice and review amendments",
            "Confirm the exact closing date, time, and submission method",
            "Verify eligibility, set-aside rules, and any contract-vehicle requirements",
            "Review statement of work, deliverables, mandatory qualifications, and evaluation criteria",
            "Assess staffing, past performance, pricing, teaming, and submission effort",
            "Record a human-approved final Bid/No-Bid decision",
        ]

        if "seaport" in " ".join(eligibility_gates).lower():
            required_checks.insert(
                2,
                "Confirm SeaPort NxG access or an eligible teaming arrangement",
            )

        if "teps iii" in " ".join(eligibility_gates).lower():
            required_checks.insert(
                2,
                "Confirm TEPS III BPA access and competition eligibility",
            )

        if not clean(row.get("qualification_decision")):
            missing_decision_count += 1

        action_counts[recommended_action] = (
            action_counts.get(recommended_action, 0) + 1
        )

        deadline_counts[deadline_status] = (
            deadline_counts.get(deadline_status, 0) + 1
        )

        output_rows.append(
            {
                "review_id": notice_id,
                "notice_id": notice_id,
                "solicitation_number": clean(
                    row.get("solicitation_number")
                ),
                "title": title,
                "agency": clean(row.get("agency")),
                "notice_type": clean(row.get("notice_type")),
                "notice_category": clean(row.get("notice_category")),
                "naics_code": clean(row.get("naics_code")),
                "set_aside": clean(row.get("set_aside")),
                "posted_date": clean(row.get("posted_date")),
                "response_deadline": clean(
                    row.get("response_deadline")
                ),
                "deadline_status": deadline_status,
                "days_until_deadline": (
                    days_until_deadline
                    if days_until_deadline is not None
                    else ""
                ),
                "qualification_decision": clean(
                    row.get("qualification_decision")
                ),
                "priority_score": clean(row.get("priority_score")),
                "capability_fit_score": clean(
                    row.get("capability_fit_score")
                ),
                "technical_score": clean(row.get("technical_score")),
                "naics_match": clean(row.get("naics_match")),
                "scope_alignment": determine_scope_alignment(row),
                "eligibility_gate": format_flags(eligibility_gates),
                "recommended_action": recommended_action,
                "risk_flags": format_flags(risk_flags),
                "required_checks": format_flags(required_checks),
                "review_status": "Pending Human Review",
                "source_url": clean(row.get("source_url")),
                "review_generated_utc": now_utc.isoformat(),
            }
        )

    # Use a new report path. Do not overwrite the qualification report.
    try:
        with OUTPUT_FILE.open(
            "w",
            encoding="utf-8-sig",
            newline="",
        ) as output_file:
            writer = csv.DictWriter(
                output_file,
                fieldnames=output_fields,
                extrasaction="ignore",
            )
            writer.writeheader()
            writer.writerows(output_rows)

    except OSError as exc:
        print(f"\nERROR: Could not write the review report: {exc}")
        print("Close the output CSV in Excel and try again.")
        return 1

    print("\nREVIEW REPORT CREATED")
    print("-" * 72)
    print(f"Input records:              {len(rows)}")
    print(f"Output records:             {len(output_rows)}")
    print(f"Missing qualification data: {missing_decision_count}")
    print(f"Output file:                {OUTPUT_FILE}")

    print("\nRECOMMENDED ACTION SUMMARY")
    print("-" * 72)

    for action, count in sorted(
        action_counts.items(),
        key=lambda item: (-item[1], item[0]),
    ):
        print(f"{action:<36} {count:>5}")

    print("\nDEADLINE STATUS SUMMARY")
    print("-" * 72)

    for status, count in sorted(
        deadline_counts.items(),
        key=lambda item: (-item[1], item[0]),
    ):
        print(f"{status:<42} {count:>5}")

    print("\nIMPORTANT")
    print(
        "These are preliminary recommendations, not final bid decisions."
    )
    print(
        "Verify current solicitation status, eligibility, and deadlines "
        "on the original notice."
    )

    print("\nNext step: inspect the highest-priority review records.")
    return 0


if __name__ == "__main__":
    sys.exit(main())