"""Capability-first ranking layer for the GovCon BD platform.

Uses the existing qualification engine and does not modify database records.
"""

from __future__ import annotations

from typing import Any

from src.qualification_engine import qualify_all_opportunities


def calculate_ranked_score(result: dict[str, Any]) -> dict[str, Any]:
    """Calculate a capability-first screening score from existing results."""

    scores = result.get("scores", {})
    naics = scores.get("naics", {})
    technical = scores.get("technical", {})
    deadline = scores.get("deadline", {})
    completeness = scores.get("completeness", {})

    naics_score = float(naics.get("score", 0) or 0)
    naics_max = max(float(naics.get("maximum", 30) or 30), 1)

    technical_score = float(technical.get("score", 0) or 0)
    technical_max = max(float(technical.get("maximum", 40) or 40), 1)

    deadline_score = float(deadline.get("score", 0) or 0)
    deadline_max = max(float(deadline.get("maximum", 20) or 20), 1)

    completeness_score = float(completeness.get("score", 0) or 0)
    completeness_max = max(float(completeness.get("maximum", 10) or 10), 1)

    naics_fit = 100 * naics_score / naics_max
    technical_fit = 100 * technical_score / technical_max
    capability_fit = 0.40 * naics_fit + 0.60 * technical_fit

    deadline_fit = 100 * deadline_score / deadline_max
    completeness_fit = 100 * completeness_score / completeness_max

    # Capability dominates the ranking; timing and completeness are secondary.
    ranked_score = (
        0.70 * capability_fit
        + 0.20 * deadline_fit
        + 0.10 * completeness_fit
    )

    flags = list(result.get("review_flags", []))

    if naics_score == 0:
        flags.append("No exact target NAICS match; verify scope and classification.")

    if technical_score == 0:
        flags.append(
            "No configured technical keywords matched; manually review "
            "the statement of work before ruling the opportunity in or out."
        )

    if capability_fit < 20:
        flags.append(
            "Low preliminary capability alignment. Do not prioritize "
            "without evidence of relevant scope or teaming potential."
        )

    category = result.get("opportunity_category", "")
    if category == "Award Notice":
        recommendation = "Award Notice - Research Award and Future Recompete"
    elif category == "Presolicitation":
        recommendation = "Monitor Presolicitation"
    elif category == "Sources Sought":
        recommendation = "Review Market Research Response Opportunity"
    elif capability_fit >= 65:
        recommendation = "High Preliminary Fit - Human Review Required"
    elif capability_fit >= 35:
        recommendation = "Review Capability and Requirements"
    else:
        recommendation = "Low or Unconfirmed Fit - Manual Review"

    result["original_total_score"] = result.get("total_score", 0)
    result["ranked_score"] = round(ranked_score, 1)
    result["ranked_score_maximum"] = 100
    result["capability_first_fit"] = round(capability_fit, 1)
    result["score_breakdown_v2"] = {
        "naics_fit_percent": round(naics_fit, 1),
        "technical_fit_percent": round(technical_fit, 1),
        "capability_fit_percent": round(capability_fit, 1),
        "deadline_fit_percent": round(deadline_fit, 1),
        "completeness_percent": round(completeness_fit, 1),
        "weights": {
            "capability_fit": 70,
            "deadline": 20,
            "completeness": 10,
        },
    }
    result["recommendation_v2"] = recommendation
    result["review_flags_v2"] = list(dict.fromkeys(flags))

    return result


def rank_opportunities() -> list[dict[str, Any]]:
    """Read existing qualification results and rerank them in memory."""

    results = qualify_all_opportunities()
    ranked = [calculate_ranked_score(dict(item)) for item in results]

    ranked.sort(
        key=lambda item: (
            item["ranked_score"],
            item["capability_first_fit"],
            item.get("opportunity_id", 0),
        ),
        reverse=True,
    )

    return ranked


def main() -> None:
    results = rank_opportunities()

    print("=" * 78)
    print("TTE CAPABILITY-FIRST OPPORTUNITY RANKING V2")
    print("=" * 78)
    print(f"Records evaluated: {len(results)}")
    print("Database mode: READ ONLY")
    print("Original qualification engine: unchanged")
    print()

    for position, item in enumerate(results[:15], start=1):
        print("-" * 78)
        print(f"Rank: {position}")
        print(f"ID: {item.get('opportunity_id')}")
        print(f"Title: {item.get('title')}")
        print(f"NAICS: {item.get('naics_code')}")
        print(f"Notice type: {item.get('opportunity_category')}")
        print(f"Original score: {item.get('original_total_score')}/100")
        print(f"New ranking score: {item.get('ranked_score')}/100")
        print(f"Capability-first fit: {item.get('capability_first_fit')}/100")
        print(f"Recommendation: {item.get('recommendation_v2')}")

        breakdown = item["score_breakdown_v2"]
        print(
            "Fit details: "
            f"NAICS {breakdown['naics_fit_percent']}%, "
            f"technical {breakdown['technical_fit_percent']}%, "
            f"deadline {breakdown['deadline_fit_percent']}%, "
            f"completeness {breakdown['completeness_percent']}%"
        )

        for flag in item["review_flags_v2"]:
            print(f"Review: {flag}")

    print()
    print("RANKING COMPLETED")
    print("No database records were modified.")


if __name__ == "__main__":
    main()
