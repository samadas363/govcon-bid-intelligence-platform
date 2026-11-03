import argparse
import csv
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
REPORTS_DIR = PROJECT_ROOT / "data" / "reports"

PRIORITY_FIELDS = [
    "priority_rank",
    "priority_level",
    "priority_group",
    "priority_action",
    "priority_reason",
    "active_bid_pipeline",
]

PRIORITY_ORDER = {
    "P1": 1,
    "P2": 2,
    "P3": 3,
    "P4": 4,
    "P5": 5,
}


def latest_qualification_report():
    files = list(
        REPORTS_DIR.glob("sam_opportunity_qualification_*.csv")
    )

    if not files:
        raise FileNotFoundError(
            "No qualification report found in data/reports."
        )

    return max(files, key=lambda f: f.stat().st_mtime)


def number(value, default=0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def classify_priority(row):
    notice_type = (
        row.get("notice_type") or ""
    ).strip().lower()

    deadline_status = (
        row.get("deadline_status") or ""
    ).strip().lower()

    recommendation = (
        row.get("qualification_recommendation") or ""
    ).strip().lower()

    score = number(row.get("qualification_total_score"))
    capability = number(row.get("capability_fit_score"))

    # Award notices are not active bidding opportunities.
    if "award" in notice_type or "award notice" in recommendation:
        return {
            "priority_rank": 5,
            "priority_level": "P5",
            "priority_group": "Award / Research Only",
            "priority_action": "Exclude from active bidding",
            "priority_reason": "Award notice; generally not an active bidding opportunity.",
            "active_bid_pipeline": "No",
        }

    # Expired deadlines must not enter the active bidding pipeline.
    if (
        "expired" in deadline_status
        or "passed" in deadline_status
        or "deadline passed" in recommendation
    ):
        return {
            "priority_rank": 5,
            "priority_level": "P5",
            "priority_group": "Expired / Verify",
            "priority_action": "Verify official notice; do not treat as active",
            "priority_reason": "The qualification report indicates that the deadline has passed or requires verification.",
            "active_bid_pipeline": "No",
        }

    # Active solicitations receive the highest priority.
    if notice_type in (
        "solicitation",
        "combined synopsis/solicitation",
        "combined synopsis solicitation",
    ):
        if (
            "within 7 days" in deadline_status
            or "due today" in deadline_status
        ):
            return {
                "priority_rank": 1,
                "priority_level": "P1",
                "priority_group": "Urgent Active Solicitation",
                "priority_action": "Review immediately; verify submission deadline and requirements",
                "priority_reason": "Active solicitation with an approaching deadline.",
                "active_bid_pipeline": "Review",
            }

        return {
            "priority_rank": 2,
            "priority_level": "P2",
            "priority_group": "Active Solicitation",
            "priority_action": "Review scope, eligibility, capability, and submission requirements",
            "priority_reason": (
                "Active solicitation. "
                f"Qualification score: {score:.0f}/100; "
                f"capability fit: {capability:.0f}/100."
            ),
            "active_bid_pipeline": "Review",
        }

    # Sources Sought and RFI opportunities are market research.
    if (
        "sources sought" in notice_type
        or "request for information" in notice_type
        or notice_type == "rfi"
    ):
        return {
            "priority_rank": 3,
            "priority_level": "P3",
            "priority_group": "Market Research / Sources Sought",
            "priority_action": "Check response instructions and consider submitting a capability response",
            "priority_reason": "Market research notice; verify whether an industry response is requested.",
            "active_bid_pipeline": "Market Research",
        }

    # Upcoming procurement notices should be monitored.
    if "presolicitation" in notice_type:
        return {
            "priority_rank": 4,
            "priority_level": "P4",
            "priority_group": "Upcoming Procurement",
            "priority_action": "Monitor for final solicitation and amendments",
            "priority_reason": "Presolicitation; monitor for the final solicitation.",
            "active_bid_pipeline": "Monitor",
        }

    # Special notices require manual inspection.
    if "special notice" in notice_type:
        return {
            "priority_rank": 4,
            "priority_level": "P4",
            "priority_group": "Special Notice / Manual Review",
            "priority_action": "Open official notice and determine whether a response or action is required",
            "priority_reason": "Special Notice requires manual review to determine its purpose and relevance.",
            "active_bid_pipeline": "Review",
        }

    # Anything not recognized is kept for manual review.
    return {
        "priority_rank": 4,
        "priority_level": "P4",
        "priority_group": "Other / Manual Review",
        "priority_action": "Manually inspect the official notice",
        "priority_reason": "Notice type was not covered by the prioritization rules.",
        "active_bid_pipeline": "Review",
    }


def main():
    parser = argparse.ArgumentParser(
        description="Prioritize TTE qualified government opportunities."
    )

    parser.add_argument(
        "--input",
        help="Optional qualification CSV path."
    )

    args = parser.parse_args()

    if args.input:
        input_file = Path(args.input)

        if not input_file.is_absolute():
            input_file = PROJECT_ROOT / input_file

        if not input_file.exists():
            raise FileNotFoundError(
                f"Input report not found: {input_file}"
            )
    else:
        input_file = latest_qualification_report()

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    output_file = (
        REPORTS_DIR
        / f"sam_opportunity_prioritization_{timestamp}.csv"
    )

    print("=" * 65)
    print("TTE OPPORTUNITY PRIORITIZATION ENGINE")
    print("=" * 65)

    print(f"Input: {input_file.name}")
    print(f"Output: {output_file.name}")

    print("\nDatabase Safety")
    print("-" * 65)
    print("PostgreSQL connection: NONE")
    print("Database reads: NONE")
    print("Database writes: NONE")

    results = []

    with input_file.open(
        "r",
        encoding="utf-8-sig",
        newline=""
    ) as source:

        reader = csv.DictReader(source)

        if not reader.fieldnames:
            raise ValueError("Input CSV has no header.")

        required = [
            "title",
            "notice_type",
            "deadline_status",
            "qualification_total_score",
            "qualification_recommendation",
        ]

        missing = [
            field for field in required
            if field not in reader.fieldnames
        ]

        if missing:
            raise ValueError(
                "Missing required columns: "
                + ", ".join(missing)
            )

        original_fields = list(reader.fieldnames)

        for row in reader:
            priority = classify_priority(row)

            combined = dict(row)
            combined.update(priority)

            results.append(combined)

    # Sort by priority first, then earliest deadline, then score.
    results.sort(
        key=lambda row: (
            row["priority_rank"],
            number(row.get("days_remaining"), 999999),
            -number(row.get("qualification_total_score")),
        )
    )

    output_fields = original_fields + [
        field for field in PRIORITY_FIELDS
        if field not in original_fields
    ]

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

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

    # Summary
    print("\nPRIORITIZATION SUMMARY")
    print("-" * 65)

    counts = {}

    for row in results:
        level = row["priority_level"]
        counts[level] = counts.get(level, 0) + 1

    for level in ["P1", "P2", "P3", "P4", "P5"]:
        print(
            f"{level}: {counts.get(level, 0)} opportunities"
        )

    print(f"\nTotal processed: {len(results)}")

    print("\nTOP 15 PRIORITIZED OPPORTUNITIES")
    print("-" * 65)

    for index, row in enumerate(results[:15], start=1):
        print(f"\n{index}. {row.get('title', '')}")
        print(
            f"   Priority: {row['priority_level']} - "
            f"{row['priority_group']}"
        )
        print(
            f"   Notice: {row.get('notice_type', '')}"
        )
        print(
            f"   Score: {row.get('qualification_total_score', '')}/100"
        )
        print(
            f"   Deadline: {row.get('response_deadline', '')}"
        )
        print(
            f"   Action: {row['priority_action']}"
        )

    print("\nOUTPUT")
    print("-" * 65)
    print(f"Saved: {output_file}")

    print("\nDatabase writes: NONE")
    print("Prioritization completed successfully.")


if __name__ == "__main__":
    main()
