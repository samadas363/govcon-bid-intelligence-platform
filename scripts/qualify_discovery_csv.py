import argparse
import csv
import json
import sys
from datetime import datetime
from pathlib import Path

# ------------------------------------------------------------
# PATHS AND IMPORTS
# ------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent
REPORTS_DIR = PROJECT_ROOT / "data" / "reports"

sys.path.insert(0, str(PROJECT_ROOT))

from src.qualification_engine import qualify_opportunity


# ------------------------------------------------------------
# CONFIGURATION
# ------------------------------------------------------------

INPUT_PATTERN = "sam_targeted_discovery_preview_*.csv"

OUTPUT_PREFIX = "sam_opportunity_qualification_"

OUTPUT_FIELDS = [
    "qualification_status",
    "qualification_total_score",
    "qualification_maximum_score",
    "capability_fit_score",
    "capability_fit_label",
    "pursuit_readiness_status",
    "qualification_recommendation",
    "active_bidding_candidate",
    "engine_opportunity_category",
    "naics_score",
    "naics_match",
    "technical_score",
    "technical_matched_groups",
    "technical_matched_keywords",
    "deadline_score",
    "deadline_status",
    "days_remaining",
    "completeness_score",
    "completeness_missing_fields",
    "classification_reason",
    "capability_fit_reason",
    "pursuit_readiness_reason",
    "review_flags",
    "qualification_error",
]


# ------------------------------------------------------------
# HELPER FUNCTIONS
# ------------------------------------------------------------

def clean_value(value):
    """Convert empty CSV values to None."""
    if value is None:
        return None

    value = str(value).strip()

    if value == "":
        return None

    return value


def json_list(values):
    """Convert lists to readable CSV strings."""
    if not values:
        return ""

    return "; ".join(str(value) for value in values)


def find_latest_discovery_csv():
    """Find the newest discovery CSV."""
    files = list(REPORTS_DIR.glob(INPUT_PATTERN))

    if not files:
        raise FileNotFoundError(
            f"No discovery CSV found in: {REPORTS_DIR}"
        )

    return max(files, key=lambda file: file.stat().st_mtime)


def normalize_opportunity(row):
    """
    Map discovery CSV columns to the field names expected
    by the existing qualification engine.
    """

    return {
        "opportunity_id": None,
        "source_record_id": clean_value(row.get("notice_id")),
        "solicitation_number": clean_value(
            row.get("solicitation_number")
        ),
        "title": clean_value(row.get("title")),
        "agency_name": clean_value(row.get("agency")),
        "opportunity_type": clean_value(row.get("notice_type")),
        "description": clean_value(row.get("description_text")),
        "naics_code": clean_value(row.get("naics_code")),
        "set_aside_type": clean_value(row.get("set_aside")),
        "place_of_performance": clean_value(
            row.get("place_of_performance")
        ),
        "response_deadline": clean_value(
            row.get("response_deadline")
        ),
        "posted_date": clean_value(row.get("posted_date")),
        "source_url": clean_value(row.get("source_url")),
        "is_sample_data": False,
    }


# ------------------------------------------------------------
# QUALIFICATION
# ------------------------------------------------------------

def qualify_row(row):
    """Qualify one discovery record using the existing engine."""

    normalized = normalize_opportunity(row)

    try:
        result = qualify_opportunity(normalized)

        scores = result.get("scores", {})
        naics = scores.get("naics", {})
        technical = scores.get("technical", {})
        deadline = scores.get("deadline", {})
        completeness = scores.get("completeness", {})

        capability = result.get("capability_fit", {})
        readiness = result.get("pursuit_readiness", {})
        classification = result.get("classification", {})

        deadline_value = deadline.get("days_remaining")

        if deadline_value is not None:
            deadline_value = round(float(deadline_value), 1)
        else:
            deadline_value = ""

        return {
            "qualification_status": "Success",

            "qualification_total_score": result.get(
                "total_score", ""
            ),

            "qualification_maximum_score": result.get(
                "maximum_score", ""
            ),

            "capability_fit_score": result.get(
                "capability_fit_score", ""
            ),

            "capability_fit_label": capability.get(
                "label", ""
            ),

            "pursuit_readiness_status": result.get(
                "pursuit_readiness_status", ""
            ),

            "qualification_recommendation": result.get(
                "recommendation", ""
            ),

            "active_bidding_candidate": result.get(
                "active_bidding_candidate", ""
            ),

            "engine_opportunity_category": result.get(
                "opportunity_category", ""
            ),

            "naics_score": naics.get("score", ""),

            "naics_match": naics.get("match", ""),

            "technical_score": technical.get("score", ""),

            "technical_matched_groups": json_list(
                technical.get("matched_groups", [])
            ),

            "technical_matched_keywords": json_list(
                technical.get("matched_keywords", [])
            ),

            "deadline_score": deadline.get("score", ""),

            "deadline_status": deadline.get("status", ""),

            "days_remaining": deadline_value,

            "completeness_score": completeness.get(
                "score", ""
            ),

            "completeness_missing_fields": json_list(
                completeness.get("missing_fields", [])
            ),

            "classification_reason": classification.get(
                "reason", ""
            ),

            "capability_fit_reason": capability.get(
                "reason", ""
            ),

            "pursuit_readiness_reason": readiness.get(
                "reason", ""
            ),

            "review_flags": json_list(
                result.get("review_flags", [])
            ),

            "qualification_error": "",
        }

    except Exception as exc:
        return {
            "qualification_status": "Failed",
            "qualification_total_score": "",
            "qualification_maximum_score": "",
            "capability_fit_score": "",
            "capability_fit_label": "",
            "pursuit_readiness_status": "",
            "qualification_recommendation": "",
            "active_bidding_candidate": "",
            "engine_opportunity_category": "",
            "naics_score": "",
            "naics_match": "",
            "technical_score": "",
            "technical_matched_groups": "",
            "technical_matched_keywords": "",
            "deadline_score": "",
            "deadline_status": "",
            "days_remaining": "",
            "completeness_score": "",
            "completeness_missing_fields": "",
            "classification_reason": "",
            "capability_fit_reason": "",
            "pursuit_readiness_reason": "",
            "review_flags": "",
            "qualification_error": str(exc),
        }


# ------------------------------------------------------------
# MAIN
# ------------------------------------------------------------

def main():

    parser = argparse.ArgumentParser(
        description="Qualify SAM.gov discovery CSV records."
    )

    parser.add_argument(
        "--input",
        type=str,
        default=None,
        help="Optional path to a specific discovery CSV."
    )

    args = parser.parse_args()

    if args.input:
        input_file = Path(args.input)

        if not input_file.is_absolute():
            input_file = PROJECT_ROOT / input_file

        if not input_file.exists():
            raise FileNotFoundError(
                f"Input CSV does not exist: {input_file}"
            )
    else:
        input_file = find_latest_discovery_csv()

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    output_file = (
        REPORTS_DIR /
        f"{OUTPUT_PREFIX}{timestamp}.csv"
    )

    print("=" * 65)
    print("TTE OPPORTUNITY QUALIFICATION")
    print("=" * 65)

    print(f"Input file: {input_file.name}")
    print(f"Output file: {output_file.name}")

    print("\nDatabase Safety")
    print("-" * 65)
    print("PostgreSQL connection: NONE")
    print("Database reads: NONE")
    print("Database writes: NONE")
    print("Existing qualification engine: READ ONLY")

    print("\nProcessing opportunities...")

    success_count = 0
    failed_count = 0
    total_count = 0

    score_total = 0
    score_count = 0

    recommendation_counts = {}

    with input_file.open(
        "r",
        encoding="utf-8-sig",
        newline=""
    ) as source:

        reader = csv.DictReader(source)

        if not reader.fieldnames:
            raise ValueError("Input CSV has no header row.")

        required_fields = [
            "title",
            "notice_type",
            "naics_code",
            "description_text",
            "response_deadline",
        ]

        missing_columns = [
            field
            for field in required_fields
            if field not in reader.fieldnames
        ]

        if missing_columns:
            raise ValueError(
                "Required CSV columns are missing: "
                + ", ".join(missing_columns)
            )

        original_fields = list(reader.fieldnames)

        output_fields = original_fields + [
            field
            for field in OUTPUT_FIELDS
            if field not in original_fields
        ]

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

                total_count += 1

                qualification = qualify_row(row)

                output_row = dict(row)
                output_row.update(qualification)

                writer.writerow(output_row)

                if qualification["qualification_status"] == "Success":

                    success_count += 1

                    score = qualification[
                        "qualification_total_score"
                    ]

                    if score != "":
                        score_total += float(score)
                        score_count += 1

                    recommendation = qualification[
                        "qualification_recommendation"
                    ] or "Not specified"

                    recommendation_counts[recommendation] = (
                        recommendation_counts.get(
                            recommendation, 0
                        ) + 1
                    )

                else:
                    failed_count += 1

                if total_count % 50 == 0:
                    print(
                        f"Processed {total_count} opportunities..."
                    )

    # --------------------------------------------------------
    # SUMMARY
    # --------------------------------------------------------

    print("\n" + "=" * 65)
    print("QUALIFICATION RESULTS")
    print("=" * 65)

    print(f"Total opportunities: {total_count}")
    print(f"Successfully qualified: {success_count}")
    print(f"Failed records: {failed_count}")

    if score_count:
        average_score = score_total / score_count

        print(
            f"Average qualification score: "
            f"{average_score:.2f}/100"
        )

    print("\nRecommendation Summary")
    print("-" * 65)

    for recommendation, count in sorted(
        recommendation_counts.items(),
        key=lambda item: item[1],
        reverse=True
    ):
        print(f"{recommendation}: {count}")

    print("\nOutput")
    print("-" * 65)
    print(f"Report saved: {output_file}")

    print("\nDatabase Safety Confirmation")
    print("-" * 65)
    print("PostgreSQL connection: NONE")
    print("Database writes: NONE")

    print("\nQualification process completed.")


if __name__ == "__main__":
    main()
