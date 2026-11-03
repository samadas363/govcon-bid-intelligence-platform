from pathlib import Path
from datetime import datetime, timezone

import pandas as pd


# ============================================================
# GOVCON BD - BID / NO-BID RECOMMENDATION ENGINE
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPORTS_DIR = PROJECT_ROOT / "data" / "reports"

INPUT_PATTERN = "sam_opportunity_bd_classification_*.csv"

MIN_QUALIFICATION_SCORE = 65
MIN_RELEVANCE_SCORE = 60
MIN_DESCRIPTION_EVIDENCE = 15

# TTE set-aside eligibility has not yet been independently verified.
VERIFY_SET_ASIDE_ELIGIBILITY = False


def clean(value):
    if pd.isna(value):
        return ""
    return str(value).strip()


def number(value, default=0):
    try:
        if pd.isna(value) or clean(value) == "":
            return default
        return float(value)
    except (ValueError, TypeError):
        return default


def is_true(value):
    return clean(value).lower() in {
        "true", "1", "yes", "y", "required"
    }


def parse_deadline(value):
    value = clean(value)

    if not value:
        return None

    try:
        return pd.to_datetime(
            value,
            errors="coerce",
            utc=True
        )
    except Exception:
        return None


def find_latest_input():
    files = list(REPORTS_DIR.glob(INPUT_PATTERN))

    if not files:
        raise FileNotFoundError(
            f"No input report found: {INPUT_PATTERN}"
        )

    return max(
        files,
        key=lambda file: file.stat().st_mtime
    )


def evaluate_opportunity(row):

    bd_class = clean(
        row.get("bd_classification")
    ).lower()

    notice_type = clean(
        row.get("notice_type")
    ).lower()

    opportunity_class = clean(
        row.get("opportunity_classification")
    ).lower()

    procurement_stage = clean(
        row.get("bd_procurement_stage")
    ).lower()

    deadline_status = clean(
        row.get("deadline_status")
    ).lower()

    qualification_score = number(
        row.get("qualification_total_score")
    )

    relevance_score = number(
        row.get("relevance_v2_score")
    )

    evidence_score = number(
        row.get("v2_description_evidence_score")
    )

    description_available = is_true(
        row.get("bd_description_available")
    )

    manual_review = (
        is_true(row.get("bd_manual_review_required"))
        or is_true(row.get("v2_manual_review_required"))
    )

    set_aside = clean(row.get("set_aside"))

    deadline = parse_deadline(
        row.get("response_deadline")
    )

    now = pd.Timestamp.now(tz="UTC")

    flags = []

    # --------------------------------------------------------
    # 1. EXPIRED OPPORTUNITIES
    # --------------------------------------------------------

    expired = (
        "passed" in deadline_status
        or "expired" in deadline_status
        or "closed" in deadline_status
        or (
            deadline is not None
            and not pd.isna(deadline)
            and deadline < now
        )
    )

    if expired:
        return {
            "bid_no_bid_decision": "NO-BID",
            "decision_confidence": "High",
            "decision_reason": "Response deadline has passed or opportunity is closed.",
            "recommended_next_action": "Do not pursue as an active bid. Retain for market intelligence.",
            "decision_review_flags": ""
        }

    # --------------------------------------------------------
    # 2. AWARD NOTICES
    # --------------------------------------------------------

    if (
        "award" in notice_type
        or "award" in opportunity_class
        or "award" in procurement_stage
    ):
        return {
            "bid_no_bid_decision": "NO-BID",
            "decision_confidence": "High",
            "decision_reason": "This appears to be an award notice rather than an active solicitation.",
            "recommended_next_action": "Review incumbent and award information for future business development.",
            "decision_review_flags": ""
        }

    # --------------------------------------------------------
    # 3. CANCELLED / WITHDRAWN NOTICES
    # --------------------------------------------------------

    if (
        "cancel" in notice_type
        or "cancel" in opportunity_class
        or "withdrawn" in opportunity_class
    ):
        return {
            "bid_no_bid_decision": "NO-BID",
            "decision_confidence": "High",
            "decision_reason": "Opportunity appears cancelled or withdrawn.",
            "recommended_next_action": "Verify the official notice.",
            "decision_review_flags": ""
        }

    # --------------------------------------------------------
    # 4. TEAMING OPPORTUNITIES
    # --------------------------------------------------------

    if "teaming" in bd_class:
        return {
            "bid_no_bid_decision": "TEAMING",
            "decision_confidence": "Medium",
            "decision_reason": clean(
                row.get("bd_classification_reason")
            ) or "Existing BD classification identifies a teaming opportunity.",
            "recommended_next_action": "Identify suitable prime contractors and assess TTE's subcontracting role.",
            "decision_review_flags": ""
        }

    # --------------------------------------------------------
    # 5. EVIDENCE AND ELIGIBILITY CHECKS
    # --------------------------------------------------------

    if "insufficient" in bd_class:
        flags.append("Insufficient BD classification evidence")

    if manual_review:
        flags.append("Manual review required by previous analysis")

    if not description_available:
        flags.append("Solicitation description unavailable")

    if evidence_score < MIN_DESCRIPTION_EVIDENCE:
        flags.append("Description evidence below threshold")

    if set_aside and not VERIFY_SET_ASIDE_ELIGIBILITY:
        flags.append(
            f"Set-aside eligibility requires verification: {set_aside}"
        )

    if not clean(row.get("response_deadline")):
        flags.append("Response deadline missing")
    elif deadline is None or pd.isna(deadline):
        flags.append("Response deadline could not be parsed")

    if qualification_score < MIN_QUALIFICATION_SCORE:
        flags.append(
            f"Qualification score below {MIN_QUALIFICATION_SCORE}"
        )

    if relevance_score < MIN_RELEVANCE_SCORE:
        flags.append(
            f"Relevance score below {MIN_RELEVANCE_SCORE}"
        )

    if bd_class not in {
        "direct tte",
        "potential direct"
    }:
        flags.append(
            f"BD classification requires review: {bd_class or 'Missing'}"
        )

    if "market research" in opportunity_class:
        flags.append("Market research notice requires separate assessment")

    if "upcoming procurement" in opportunity_class:
        flags.append("Upcoming procurement should be monitored")

    if "specialized" in bd_class:
        flags.append("Specialized opportunity requires technical review")

    # --------------------------------------------------------
    # 6. FINAL RECOMMENDATION
    # --------------------------------------------------------

    if flags:

        decision = "REVIEW"

        confidence = (
            "Low" if len(flags) >= 3 else "Medium"
        )

        reason = (
            "One or more evidence, eligibility, "
            "or readiness checks require review."
        )

        next_action = (
            "Review the official solicitation, confirm eligibility, "
            "validate requirements and deadline, then make a human decision."
        )

    else:

        decision = "BID"

        confidence = "Medium"

        reason = (
            "Qualification, relevance, description evidence, "
            "and BD classification meet the initial bid-candidate thresholds."
        )

        next_action = (
            "Conduct final solicitation review, prepare compliance "
            "requirements, and obtain management approval."
        )

    return {
        "bid_no_bid_decision": decision,
        "decision_confidence": confidence,
        "decision_reason": reason,
        "recommended_next_action": next_action,
        "decision_review_flags": " | ".join(flags)
    }


def main():

    print("=" * 65)
    print("GOVCON BID / NO-BID RECOMMENDATION ENGINE")
    print("=" * 65)

    input_file = find_latest_input()

    print(f"\nInput file: {input_file.name}")

    df = pd.read_csv(
        input_file,
        dtype=str,
        keep_default_na=False
    )

    if df.empty:
        raise ValueError("Input CSV is empty.")

    required_columns = [
        "notice_id",
        "qualification_total_score",
        "relevance_v2_score",
        "bd_classification"
    ]

    missing = [
        col for col in required_columns
        if col not in df.columns
    ]

    if missing:
        raise ValueError(
            f"Missing required columns: {missing}"
        )

    print(f"Opportunities loaded: {len(df)}")
    print("Generating recommendations...")

    results = df.apply(
        evaluate_opportunity,
        axis=1
    )

    result_df = pd.DataFrame(
        results.tolist(),
        index=df.index
    )

    output = pd.concat(
        [df, result_df],
        axis=1
    )

    output["decision_generated_at"] = (
        datetime.now(timezone.utc).isoformat()
    )

    timestamp = datetime.now().strftime(
        "%Y%m%d_%H%M%S"
    )

    output_file = REPORTS_DIR / (
        f"sam_bid_no_bid_recommendations_{timestamp}.csv"
    )

    output.to_csv(
        output_file,
        index=False,
        encoding="utf-8-sig"
    )

    print("\n" + "=" * 65)
    print("ANALYSIS COMPLETE")
    print("=" * 65)

    summary = output[
        "bid_no_bid_decision"
    ].value_counts()

    for decision in [
        "BID",
        "NO-BID",
        "TEAMING",
        "REVIEW"
    ]:
        print(
            f"{decision}: {summary.get(decision, 0)}"
        )

    print(f"\nTotal opportunities: {len(output)}")
    print(f"Report saved: {output_file}")

    print("\nPostgreSQL was not accessed or modified.")


if __name__ == "__main__":
    main()