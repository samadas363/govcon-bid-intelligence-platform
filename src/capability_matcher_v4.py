"""
Capability Matcher V4
Conservative ranking for Tiger Team Engineering.

- Preserves V1, V2, and V3.
- Does not modify PostgreSQL records.
- Suppresses technical-fit credit for likely product purchases
  outside the configured target NAICS list.
- Preserves original evidence and explains every suppression.
"""

import json
import re

from src.database import fetch_all
from src.capability_matcher_v3 import match_capabilities_v3, is_likely_product_purchase


def detect_product_purchase(opportunity):
    """Detect likely supply-item solicitations using title patterns."""
    title = str(opportunity.get("title") or "").strip()

    # Common federal supply-class title pattern, e.g. 41--COMPRESSOR.
    federal_supply_title = bool(
        re.match(r"^\s*\d{2}\s*--", title)
    )

    return is_likely_product_purchase(title) or federal_supply_title


def match_capabilities_v4(opportunity):
    """Apply conservative ranking rules without modifying the V3 result."""
    base = match_capabilities_v3(opportunity)
    result = dict(base)

    target_naics_match = bool(result.get("target_naics_match"))
    product_purchase = detect_product_purchase(opportunity)

    original_technical_score = float(result.get("technical_score") or 0.0)
    original_evidence = result.get("matched_evidence") or {}
    original_groups = list(result.get("matched_keyword_groups") or [])

    result["matcher_version"] = "V4"
    result["likely_product_purchase"] = product_purchase
    result["original_technical_score"] = original_technical_score
    result["original_matched_keyword_groups"] = original_groups
    result["original_matched_evidence"] = original_evidence

    flags = list(result.get("review_flags") or [])

    # Conservative rule: do not treat generic text in a likely product
    # solicitation as evidence of service capability when its NAICS is
    # outside the company's configured target list.
    suppress_product_match = product_purchase and not target_naics_match

    if suppress_product_match:
        result["technical_score"] = 0.0
        result["matched_keyword_groups"] = []
        result["matched_evidence"] = {}
        result["capability_fit_score"] = 0.0
        result["fit_label"] = (
            "Likely Product Purchase - Outside Target NAICS"
        )
        result["preliminary_priority"] = (
            "Low priority; review manually if the company supplies this item"
        )
        flags.append(
            "Technical score suppressed for conservative ranking because "
            "the title resembles a product purchase and the NAICS is outside "
            "the configured target list. Original evidence is preserved."
        )
    else:
        technical_score = float(result.get("technical_score") or 0.0)

        # Capability fit remains separate from deadlines and data completeness.
        capability_fit = (
            (40.0 if target_naics_match else 0.0)
            + (0.60 * technical_score)
        )
        result["capability_fit_score"] = round(
            min(100.0, capability_fit), 1
        )

        if target_naics_match and technical_score > 0:
            result["fit_label"] = "NAICS and Technical Evidence Match"
            result["preliminary_priority"] = "Review for qualification"
        elif target_naics_match:
            result["fit_label"] = (
                "NAICS Match - Technical Fit Unconfirmed"
            )
            result["preliminary_priority"] = "Investigate scope"
        elif technical_score > 0:
            result["fit_label"] = (
                "Technical Evidence Found - NAICS Mismatch"
            )
            result["preliminary_priority"] = (
                "Manual review; verify NAICS relevance"
            )
        else:
            result["fit_label"] = "No Confirmed Capability Match"
            result["preliminary_priority"] = (
                "Low priority unless other evidence supports fit"
            )

    # A separate ranking score ensures target-NAICS matches are considered
    # before unsupported matches outside the target list.
    result["ranking_score"] = round(
        float(result.get("capability_fit_score") or 0.0), 1
    )
    result["review_flags"] = sorted(set(flags))

    return result


def main():
    print("=" * 78)
    print("CAPABILITY MATCHER V4")
    print("=" * 78)
    print("Mode: READ-ONLY")
    print("Database changes: NONE")
    print()

    rows = fetch_all(
        """
        SELECT *
        FROM public.opportunities
        WHERE COALESCE(is_sample_data, FALSE) = FALSE
        ORDER BY opportunity_id DESC
        """
    )

    results = [match_capabilities_v4(row) for row in rows]
    results.sort(
        key=lambda item: (
            item["ranking_score"],
            bool(item.get("target_naics_match")),
            float(item.get("technical_score") or 0.0),
        ),
        reverse=True,
    )

    print(f"REAL OPPORTUNITIES TESTED: {len(results)}")
    print(
        "TARGET NAICS MATCHES:",
        sum(bool(r.get("target_naics_match")) for r in results),
    )
    print(
        "LIKELY PRODUCT PURCHASES:",
        sum(bool(r.get("likely_product_purchase")) for r in results),
    )
    print(
        "PRODUCT MATCHES SUPPRESSED:",
        sum(
            bool(r.get("likely_product_purchase"))
            and not bool(r.get("target_naics_match"))
            for r in results
        ),
    )
    print(
        "ZERO TECHNICAL SCORES:",
        sum(float(r.get("technical_score") or 0) == 0 for r in results),
    )

    print("\nTOP 10 BY V4 RANKING SCORE")
    for item in results[:10]:
        print(
            json.dumps(
                {
                    "id": item.get("opportunity_id"),
                    "title": item.get("title"),
                    "naics": item.get("naics_code"),
                    "naics_match": item.get("target_naics_match"),
                    "ranking_score": item.get("ranking_score"),
                    "capability_fit": item.get("capability_fit_score"),
                    "technical_score": item.get("technical_score"),
                    "original_technical_score": item.get(
                        "original_technical_score"
                    ),
                    "product_purchase": item.get(
                        "likely_product_purchase"
                    ),
                    "label": item.get("fit_label"),
                    "priority": item.get("preliminary_priority"),
                    "flags": item.get("review_flags"),
                },
                default=str,
            )
        )

    print("\nFIRF OPPORTUNITY CHECK")
    firf = [
        item for item in results
        if "FIRF" in str(item.get("title") or "").upper()
    ]

    if firf:
        for item in firf:
            print(
                json.dumps(
                    {
                        "id": item.get("opportunity_id"),
                        "title": item.get("title"),
                        "naics": item.get("naics_code"),
                        "naics_match": item.get("target_naics_match"),
                        "ranking_score": item.get("ranking_score"),
                        "technical_score": item.get("technical_score"),
                        "eligibility": item.get("eligibility_status"),
                        "label": item.get("fit_label"),
                        "flags": item.get("review_flags"),
                    },
                    default=str,
                )
            )
    else:
        print("FIRF opportunity not found.")

    print("\nCompleted. No database records were changed.")


if __name__ == "__main__":
    main()
