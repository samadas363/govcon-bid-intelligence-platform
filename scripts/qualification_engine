"""
TTE Opportunity Qualification Engine
GovCon BD Intelligence & Automation Platform

Purpose:
    Evaluate SAM.gov opportunities against the Tiger Team
    Engineering (TTE) company profile.

Scoring:
    NAICS alignment:             30 points
    Technical keyword alignment: 40 points
    Deadline assessment:         20 points
    Data completeness:           10 points
    Maximum overall score:      100 points

Capability Fit Score:
    A separate normalized score based only on NAICS and
    technical keyword alignment.

Opportunity types:
    Solicitation
    Combined Synopsis/Solicitation
    Presolicitation
    Sources Sought
    Award Notice

Safety:
    - Reads opportunities from PostgreSQL.
    - Does not insert, update, or delete database records.
    - Does not independently verify certifications or eligibility.
    - Does not submit bids.
    - Produces preliminary screening recommendations only.
"""

from datetime import date, datetime, timezone
from typing import Any

from src.company_profile import get_company_profile
from src.database import fetch_all


# ============================================================
# CONFIGURATION
# ============================================================

PROFILE = get_company_profile()

SCORING = PROFILE["qualification_settings"]

MAX_SCORE = SCORING["maximum_score"]
NAICS_WEIGHT = SCORING["naics_match_weight"]
TECHNICAL_WEIGHT = SCORING["technical_match_weight"]
DEADLINE_WEIGHT = SCORING["deadline_weight"]
COMPLETENESS_WEIGHT = SCORING["data_completeness_weight"]

TARGET_NAICS = {
    str(code).strip()
    for code in PROFILE["target_naics_codes"]
}

KEYWORD_GROUPS = PROFILE["keyword_groups"]

CAPABILITY_WEIGHT = NAICS_WEIGHT + TECHNICAL_WEIGHT


# ============================================================
# GENERAL HELPERS
# ============================================================

def normalize_text(value: Any) -> str:
    """Convert a value to normalized lowercase text."""
    if value is None:
        return ""

    return str(value).strip().lower()


def normalize_naics(value: Any) -> str:
    """Normalize a NAICS code without partial matching."""
    if value is None:
        return ""

    text = str(value).strip()

    if text.endswith(".0"):
        text = text[:-2]

    return text


def get_field(record: dict, *names: str, default=None):
    """Read a field using one or more possible field names."""
    for name in names:
        if name in record and record[name] is not None:
            return record[name]

    return default


def parse_datetime(value: Any):
    """
    Convert supported date/time values to timezone-aware UTC.

    Naive database timestamps are interpreted as UTC for this
    preliminary assessment, consistent with the existing engine.
    """
    if value is None or value == "":
        return None

    if isinstance(value, datetime):
        parsed = value

    elif isinstance(value, date):
        parsed = datetime.combine(
            value,
            datetime.min.time(),
        )

    else:
        text = str(value).strip()

        if not text:
            return None

        try:
            parsed = datetime.fromisoformat(
                text.replace("Z", "+00:00")
            )
        except ValueError:
            return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)

    return parsed.astimezone(timezone.utc)


def current_utc():
    """Return the current UTC timestamp."""
    return datetime.now(timezone.utc)


# ============================================================
# OPPORTUNITY CLASSIFICATION
# ============================================================

def classify_opportunity(opportunity: dict) -> dict:
    """
    Classify an opportunity according to its published type.

    Classification is based on the stored opportunity_type.
    The official solicitation must be checked before action.

    Award notices are classified as research-only records.
    They are not treated as active bidding opportunities.
    """
    raw_type = get_field(
        opportunity,
        "opportunity_type",
        default="",
    )

    normalized_type = normalize_text(raw_type)

    if "award notice" in normalized_type:
        category = "Award Notice"
        action = "Research Only"
        active_bidding = False
        explanation = (
            "Award notice: do not treat this record as an open "
            "bid. Use it for market, incumbent, or award research."
        )

    elif "sources sought" in normalized_type:
        category = "Sources Sought"
        action = "Evaluate Market Research Response"
        active_bidding = False
        explanation = (
            "Sources Sought: review the notice for a capability "
            "statement or market-research response opportunity. "
            "This is not automatically a solicitation."
        )

    elif "presolicitation" in normalized_type:
        category = "Presolicitation"
        action = "Monitor for Solicitation"
        active_bidding = False
        explanation = (
            "Presolicitation: monitor for the final solicitation, "
            "requirements, amendments, and response deadline."
        )

    elif (
        "combined synopsis" in normalized_type
        or "solicitation" in normalized_type
    ):
        category = "Solicitation"
        action = "Evaluate for Potential Bid"
        active_bidding = True
        explanation = (
            "Potential bidding opportunity. Verify the official "
            "notice, requirements, amendments, and deadline."
        )

    else:
        category = "Other / Unclassified"
        action = "Manual Review Required"
        active_bidding = False
        explanation = (
            "The stored opportunity type was not recognized. "
            "Review the official notice before deciding how to proceed."
        )

    return {
        "raw_type": raw_type,
        "category": category,
        "recommended_action": action,
        "active_bidding_candidate": active_bidding,
        "reason": explanation,
    }


# ============================================================
# NAICS ALIGNMENT
# ============================================================

def score_naics(opportunity: dict) -> dict:
    """Score exact alignment with configured target NAICS codes."""
    naics_value = get_field(
        opportunity,
        "naics_code",
        "naics",
    )

    opportunity_naics = normalize_naics(naics_value)

    if not opportunity_naics:
        return {
            "score": 0,
            "maximum": NAICS_WEIGHT,
            "match": False,
            "opportunity_naics": None,
            "matched_naics": None,
            "reason": "Opportunity NAICS code is missing.",
        }

    if opportunity_naics in TARGET_NAICS:
        return {
            "score": NAICS_WEIGHT,
            "maximum": NAICS_WEIGHT,
            "match": True,
            "opportunity_naics": opportunity_naics,
            "matched_naics": opportunity_naics,
            "reason": f"Exact NAICS match: {opportunity_naics}.",
        }

    return {
        "score": 0,
        "maximum": NAICS_WEIGHT,
        "match": False,
        "opportunity_naics": opportunity_naics,
        "matched_naics": None,
        "reason": (
            f"NAICS {opportunity_naics} does not exactly match "
            "TTE's configured target NAICS codes."
        ),
    }


# ============================================================
# TECHNICAL ALIGNMENT
# ============================================================

def build_opportunity_text(opportunity: dict) -> str:
    """Combine selected opportunity fields for keyword matching."""
    fields = [
        "title",
        "description",
        "opportunity_type",
        "solicitation_number",
    ]

    values = []

    for field in fields:
        value = opportunity.get(field)

        if value:
            values.append(str(value))

    return " ".join(values).lower()


def score_technical_fit(opportunity: dict) -> dict:
    """
    Evaluate technical alignment using configured keyword groups.

    This is transparent substring matching, not semantic AI
    evaluation or proof of actual technical capability.
    """
    text = build_opportunity_text(opportunity)

    if not text.strip():
        return {
            "score": 0,
            "maximum": TECHNICAL_WEIGHT,
            "matched_groups": [],
            "matched_keywords": [],
            "reason": (
                "Opportunity title and description are missing."
            ),
        }

    matched_groups = []
    matched_keywords = []

    for group_name, keywords in KEYWORD_GROUPS.items():
        group_matches = []

        for keyword in keywords:
            normalized_keyword = normalize_text(keyword)

            if normalized_keyword and normalized_keyword in text:
                group_matches.append(keyword)

        if group_matches:
            matched_groups.append(group_name)
            matched_keywords.extend(group_matches)

    total_groups = len(KEYWORD_GROUPS)

    if total_groups == 0:
        score = 0
    else:
        score = round(
            TECHNICAL_WEIGHT
            * len(matched_groups)
            / total_groups
        )

    score = min(TECHNICAL_WEIGHT, score)

    if matched_groups:
        reason = (
            f"Matched {len(matched_groups)} of "
            f"{total_groups} technical keyword groups."
        )
    else:
        reason = (
            "No configured technical keywords were found "
            "in the opportunity text. This does not prove "
            "that the opportunity is technically unsuitable."
        )

    return {
        "score": score,
        "maximum": TECHNICAL_WEIGHT,
        "matched_groups": matched_groups,
        "matched_keywords": sorted(set(matched_keywords)),
        "reason": reason,
    }


# ============================================================
# DEADLINE ASSESSMENT
# ============================================================

def score_deadline(
    opportunity: dict,
    reference_time=None,
) -> dict:
    """
    Assess the stored response deadline.

    More than 30 days remaining: 20 points
    8-30 days remaining:         15 points
    1-7 days remaining:           8 points
    Deadline passed:              0 points
    Missing/unparseable:           5 points

    A deadline score is not proof that the notice is open.
    """
    if reference_time is None:
        reference_time = current_utc()
    else:
        reference_time = parse_datetime(reference_time)

        if reference_time is None:
            raise ValueError(
                "reference_time must be a valid datetime."
            )

    deadline_value = get_field(
        opportunity,
        "response_deadline",
    )

    deadline = parse_datetime(deadline_value)

    if deadline is None:
        return {
            "score": 5,
            "maximum": DEADLINE_WEIGHT,
            "deadline": None,
            "days_remaining": None,
            "status": "Missing or unparseable",
            "reason": (
                "Deadline is missing or could not be interpreted. "
                "Verify the official notice."
            ),
        }

    seconds_remaining = (
        deadline - reference_time
    ).total_seconds()

    days_remaining = seconds_remaining / 86400

    if seconds_remaining <= 0:
        return {
            "score": 0,
            "maximum": DEADLINE_WEIGHT,
            "deadline": deadline,
            "days_remaining": 0,
            "status": "Past deadline",
            "reason": (
                "The stored deadline has passed. Check the official "
                "notice and amendments before considering pursuit."
            ),
        }

    if days_remaining <= 7:
        score = 8
        status = "Due within 7 days"

    elif days_remaining <= 30:
        score = 15
        status = "Due within 30 days"

    else:
        score = 20
        status = "More than 30 days remaining"

    return {
        "score": score,
        "maximum": DEADLINE_WEIGHT,
        "deadline": deadline,
        "days_remaining": round(days_remaining, 1),
        "status": status,
        "reason": (
            f"{status}; approximately "
            f"{round(days_remaining, 1)} days remain."
        ),
    }


# ============================================================
# DATA COMPLETENESS
# ============================================================

def score_data_completeness(opportunity: dict) -> dict:
    """Score the presence of key opportunity information."""
    checks = [
        ("title", 2),
        ("description", 2),
        ("naics_code", 2),
        ("response_deadline", 2),
        ("agency_name", 1),
        ("source_url", 1),
    ]

    score = 0
    present_fields = []
    missing_fields = []

    for field, points in checks:
        value = opportunity.get(field)

        if value is None or not str(value).strip():
            missing_fields.append(field)
        else:
            score += points
            present_fields.append(field)

    score = min(COMPLETENESS_WEIGHT, score)

    if missing_fields:
        reason = (
            "Missing fields: "
            + ", ".join(missing_fields)
            + "."
        )
    else:
        reason = "All configured completeness fields are present."

    return {
        "score": score,
        "maximum": COMPLETENESS_WEIGHT,
        "present_fields": present_fields,
        "missing_fields": missing_fields,
        "reason": reason,
    }


# ============================================================
# CAPABILITY FIT
# ============================================================

def calculate_capability_fit(
    naics_result: dict,
    technical_result: dict,
) -> dict:
    """
    Calculate a normalized capability fit score from 0 to 100.

    Capability fit uses only NAICS and technical keyword scores.
    Deadline and data completeness are deliberately excluded.

    A score is a preliminary screening indicator, not a bid decision.
    """
    raw_score = (
        naics_result["score"]
        + technical_result["score"]
    )

    if CAPABILITY_WEIGHT <= 0:
        normalized_score = 0
    else:
        normalized_score = round(
            100 * raw_score / CAPABILITY_WEIGHT
        )

    normalized_score = max(
        0,
        min(100, normalized_score),
    )

    if normalized_score >= 70:
        label = "Higher preliminary capability alignment"
    elif normalized_score >= 40:
        label = "Partial preliminary capability alignment"
    else:
        label = "Low or unconfirmed capability alignment"

    return {
        "score": normalized_score,
        "maximum": 100,
        "raw_score": raw_score,
        "raw_maximum": CAPABILITY_WEIGHT,
        "label": label,
        "reason": (
            "Based on configured NAICS and keyword matching only. "
            "Review the actual statement of work and TTE's experience."
        ),
    }


# ============================================================
# PURSUIT READINESS
# ============================================================

def assess_pursuit_readiness(
    opportunity: dict,
    classification: dict,
    deadline_result: dict,
    capability_fit: dict,
) -> dict:
    """
    Provide a separate action-oriented assessment.

    This does not establish legal eligibility or prove that a notice
    is still open. Official notice verification is always required.
    """
    category = classification["category"]
    deadline_status = deadline_result["status"]

    if category == "Award Notice":
        status = "Research Only"
        reason = (
            "Award Notice records are not included as active bidding "
            "opportunities. Use this record for market research."
        )

    elif category == "Sources Sought":
        status = "Evaluate Market Research Response"
        reason = (
            "Review the notice for a capability statement, "
            "market-research response, and its stated due date."
        )

    elif category == "Presolicitation":
        status = "Monitor for Solicitation"
        reason = (
            "Monitor for the final solicitation and confirm the "
            "requirements and response deadline when published."
        )

    elif category == "Other / Unclassified":
        status = "Manual Review Required"
        reason = (
            "Verify the opportunity type and intended action "
            "against the official notice."
        )

    elif deadline_status == "Past deadline":
        status = "Deadline Passed - Verify Official Notice"
        reason = (
            "The stored deadline has passed. Check amendments or "
            "a revised deadline before deciding whether to proceed."
        )

    elif deadline_status == "Missing or unparseable":
        status = "Verify Deadline Before Pursuit"
        reason = (
            "A response deadline could not be confirmed from the "
            "stored record. Verify the official notice first."
        )

    elif capability_fit["score"] >= 70:
        status = "Potential Pursuit - Human Review"
        reason = (
            "Preliminary capability alignment is relatively high. "
            "Review the solicitation, eligibility, workload, "
            "contract terms, and submission requirements."
        )

    elif capability_fit["score"] >= 40:
        status = "Review Capability and Requirements"
        reason = (
            "Some capability alignment was identified. Review the "
            "statement of work and confirm whether TTE can perform it."
        )

    else:
        status = "Low or Unconfirmed Fit - Manual Review"
        reason = (
            "The configured NAICS and keyword rules found limited "
            "alignment. Manually review the scope before deciding "
            "whether to pursue or decline."
        )

    return {
        "status": status,
        "reason": reason,
    }


# ============================================================
# OVERALL QUALIFICATION
# ============================================================

def qualify_opportunity(
    opportunity: dict,
    reference_time=None,
) -> dict:
    """
    Produce a complete preliminary qualification result.

    Retains the existing result fields and adds:
        opportunity_category
        classification
        capability_fit
        pursuit_readiness
    """
    if not isinstance(opportunity, dict):
        raise TypeError("opportunity must be a dictionary.")

    naics_result = score_naics(opportunity)

    technical_result = score_technical_fit(opportunity)

    deadline_result = score_deadline(
        opportunity,
        reference_time=reference_time,
    )

    completeness_result = score_data_completeness(
        opportunity
    )

    classification = classify_opportunity(opportunity)

    capability_fit = calculate_capability_fit(
        naics_result,
        technical_result,
    )

    total_score = (
        naics_result["score"]
        + technical_result["score"]
        + deadline_result["score"]
        + completeness_result["score"]
    )

    total_score = max(
        0,
        min(MAX_SCORE, total_score),
    )

    readiness = assess_pursuit_readiness(
        opportunity,
        classification,
        deadline_result,
        capability_fit,
    )

    # Preserve the existing recommendation concept, but prevent
    # non-solicitation types from being presented as active bids.
    if classification["category"] == "Award Notice":
        recommendation = "Research Only - Award Notice"

    elif classification["category"] == "Sources Sought":
        recommendation = "Review for Market Research Response"

    elif classification["category"] == "Presolicitation":
        recommendation = "Monitor for Solicitation"

    elif classification["category"] == "Other / Unclassified":
        recommendation = "Manual Review Required"

    elif deadline_result["status"] == "Past deadline":
        recommendation = "Deadline Passed - Verify Official Notice"

    elif deadline_result["status"] == "Missing or unparseable":
        recommendation = "Verify Deadline Before Pursuit"

    elif capability_fit["score"] >= 70:
        recommendation = "Potential Pursuit - Human Review"

    elif capability_fit["score"] >= 40:
        recommendation = "Review Capability and Requirements"

    else:
        recommendation = "Low or Unconfirmed Fit - Manual Review"

    review_flags = []

    if not naics_result["match"]:
        review_flags.append(
            "No exact target NAICS match; verify the classification."
        )

    if deadline_result["status"] == "Past deadline":
        review_flags.append(
            "Stored response deadline has passed."
        )

    elif deadline_result["status"] == "Missing or unparseable":
        review_flags.append(
            "Response deadline requires verification."
        )

    if completeness_result["missing_fields"]:
        review_flags.append(
            "Opportunity information is incomplete."
        )

    if classification["category"] == "Award Notice":
        review_flags.append(
            "Award Notice: excluded from the active bidding shortlist."
        )

    elif classification["category"] == "Presolicitation":
        review_flags.append(
            "Presolicitation: monitor for a final solicitation."
        )

    elif classification["category"] == "Sources Sought":
        review_flags.append(
            "Sources Sought: check whether a capability response is requested."
        )

    elif classification["category"] == "Other / Unclassified":
        review_flags.append(
            "Opportunity type is unclassified; verify the official notice."
        )

    if opportunity.get("is_sample_data"):
        review_flags.append(
            "SAMPLE RECORD: Do not treat as a live opportunity."
        )

    review_flags.append(
        "Verify the official notice, requirements, amendments, "
        "submission deadline, and TTE eligibility before a bid decision."
    )

    return {
        "opportunity_id": get_field(
            opportunity,
            "opportunity_id",
        ),
        "title": get_field(
            opportunity,
            "title",
            default="Untitled opportunity",
        ),
        "agency_name": get_field(
            opportunity,
            "agency_name",
            default="Agency not provided",
        ),
        "solicitation_number": get_field(
            opportunity,
            "solicitation_number",
        ),
        "naics_code": get_field(
            opportunity,
            "naics_code",
        ),
        "opportunity_type": get_field(
            opportunity,
            "opportunity_type",
        ),
        "opportunity_category": classification["category"],
        "classification": classification,
        "active_bidding_candidate": (
            classification["active_bidding_candidate"]
        ),
        "is_sample_data": bool(
            opportunity.get("is_sample_data", False)
        ),
        "total_score": total_score,
        "maximum_score": MAX_SCORE,
        "capability_fit": capability_fit,
        "capability_fit_score": capability_fit["score"],
        "pursuit_readiness": readiness,
        "pursuit_readiness_status": readiness["status"],
        "recommendation": recommendation,
        "scores": {
            "naics": naics_result,
            "technical": technical_result,
            "deadline": deadline_result,
            "completeness": completeness_result,
        },
        "matched_keywords": technical_result["matched_keywords"],
        "matched_keyword_groups": technical_result["matched_groups"],
        "review_flags": review_flags,
    }


# ============================================================
# DATABASE INTEGRATION
# ============================================================

def load_opportunities_for_qualification(
    include_samples=False,
) -> list:
    """
    Load opportunities from PostgreSQL.

    Sample records are excluded by default.

    This function only performs a SELECT query.
    """
    query = """
        SELECT
            opportunity_id,
            source_name,
            source_record_id,
            solicitation_number,
            title,
            agency_name,
            opportunity_type,
            description,
            naics_code,
            set_aside_type,
            place_of_performance,
            estimated_value,
            posted_date,
            response_deadline,
            status,
            source_url,
            is_sample_data,
            created_at,
            updated_at
        FROM public.opportunities
    """

    if not include_samples:
        query += """
            WHERE COALESCE(is_sample_data, FALSE) = FALSE
        """

    query += """
        ORDER BY
            posted_date DESC NULLS LAST,
            opportunity_id DESC
    """

    records = fetch_all(query)

    return [dict(record) for record in records]


def qualify_all_opportunities(
    include_samples=False,
    reference_time=None,
) -> list:
    """
    Score database opportunities without modifying records.

    Results are sorted by overall score, highest first.
    """
    opportunities = load_opportunities_for_qualification(
        include_samples=include_samples
    )

    results = [
        qualify_opportunity(
            opportunity,
            reference_time=reference_time,
        )
        for opportunity in opportunities
    ]

    results.sort(
        key=lambda result: (
            result["total_score"],
            result["opportunity_id"] or 0,
        ),
        reverse=True,
    )

    return results


# ============================================================
# COMMAND-LINE REPORT
# ============================================================

def main():
    print("=" * 76)
    print("TTE OPPORTUNITY QUALIFICATION ENGINE")
    print("=" * 76)

    print(f"Company: {PROFILE['company_name']}")
    print(f"Target NAICS codes: {len(TARGET_NAICS)}")
    print(f"Technical keyword groups: {len(KEYWORD_GROUPS)}")
    print(f"Maximum overall score: {MAX_SCORE}")
    print("Database mode: READ ONLY")

    print("\nLoading real opportunity records from PostgreSQL...")

    try:
        results = qualify_all_opportunities(
            include_samples=False,
        )

    except Exception as exc:
        print("\nQUALIFICATION FAILED")
        print(f"Error type: {type(exc).__name__}")
        print(f"Error details: {exc}")
        raise

    print(f"\nReal records evaluated: {len(results)}")

    if not results:
        print("No real opportunity records were found.")
        return

    # Summary by opportunity type.
    category_counts = {}

    for result in results:
        category = result["opportunity_category"]
        category_counts[category] = (
            category_counts.get(category, 0) + 1
        )

    print("\nOPPORTUNITY TYPE SUMMARY")
    print("-" * 76)

    for category, count in sorted(
        category_counts.items(),
        key=lambda item: (-item[1], item[0]),
    ):
        print(f"{category}: {count}")

    # Summary of potential active bidding candidates.
    active_candidates = [
        result
        for result in results
        if result["active_bidding_candidate"]
    ]

    print(
        "\nPotential solicitation records requiring review: "
        f"{len(active_candidates)}"
    )

    print("\nTOP 10 RESULTS BY OVERALL SCREENING SCORE")
    print("-" * 76)

    for result in results[:10]:
        print(
            f"\nID: {result['opportunity_id']}"
            f"\nTitle: {result['title']}"
            f"\nAgency: {result['agency_name']}"
            f"\nOpportunity type: {result['opportunity_category']}"
            f"\nNAICS: {result['naics_code']}"
            f"\nOverall score: {result['total_score']}/"
            f"{result['maximum_score']}"
            f"\nCapability fit: "
            f"{result['capability_fit_score']}/100"
            f"\nPursuit readiness: "
            f"{result['pursuit_readiness_status']}"
            f"\nRecommendation: {result['recommendation']}"
        )

        print("Factor scores:")

        for factor_name, factor in result["scores"].items():
            print(
                f"  {factor_name.title()}: "
                f"{factor['score']}/{factor['maximum']}"
            )

        if result["matched_keywords"]:
            print(
                "Matched keywords: "
                + ", ".join(result["matched_keywords"][:8])
            )

        if result["review_flags"]:
            print("Review flags:")

            for flag in result["review_flags"]:
                print(f"  - {flag}")

        print("-" * 76)

    print("\nQUALIFICATION COMPLETED")
    print("No database records were modified.")


if __name__ == "__main__":
    main()