"""
Capability Matcher V3
Purpose:
- Reduce false positives from generic procurement-related terms.
- Detect likely product-purchase solicitations.
- Separate NAICS alignment from technical evidence.
- Provide transparent evidence and review flags.
- Read-only: does not modify database records.
"""

import re
import json

from src.database import fetch_all
from src.capability_matcher_v2 import match_capabilities


# Generic phrases that are insufficient on their own to establish technical fit.
GENERIC_TERMS = {
    "procurement",
    "management",
    "support",
    "services",
    "analysis",
    "technical support",
    "business services",
    "professional services",
}

# Common indicators of product or equipment purchases.
PRODUCT_TITLE_TERMS = {
    "assembly",
    "cartridge",
    "compressor",
    "pump",
    "washer",
    "dryer",
    "filter element",
    "disk",
    "disc",
    "toner",
    "fountain",
    "diffuser",
    "light",
    "valve",
    "bearing",
    "bolt",
    "screw",
    "bracket",
    "cable",
    "hose",
    "motor",
    "battery",
    "refrigerator",
    "equipment",
    "supplies",
    "parts kit",
    "replacement part",
    "fluid",
}


def normalize_text(value):
    """Normalize text for consistent phrase comparisons."""
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value).lower()).strip()


def is_likely_product_purchase(title):
    """Flag titles containing common product or equipment indicators."""
    normalized = normalize_text(title)
    return any(term in normalized for term in PRODUCT_TITLE_TERMS)


def get_evidence_phrases(result):
    """Flatten matched evidence phrases from the V2 result."""
    evidence = result.get("matched_evidence") or {}
    phrases = []

    if isinstance(evidence, dict):
        for group_phrases in evidence.values():
            if isinstance(group_phrases, (list, tuple, set)):
                phrases.extend(str(p).strip() for p in group_phrases if p)
            elif group_phrases:
                phrases.append(str(group_phrases).strip())

    return sorted(set(phrases))


def has_meaningful_technical_evidence(result):
    """
    Return True when at least one matched phrase contains meaningful
    evidence beyond generic business terms.
    """
    phrases = get_evidence_phrases(result)

    for phrase in phrases:
        normalized = normalize_text(phrase)

        if not normalized:
            continue

        if normalized in GENERIC_TERMS:
            continue

        # Reject a phrase made up only of generic terms.
        words = set(re.findall(r"[a-z]+", normalized))
        generic_words = set()

        for term in GENERIC_TERMS:
            generic_words.update(re.findall(r"[a-z]+", term))

        if words and words.issubset(generic_words):
            continue

        return True

    return False


def match_capabilities_v3(opportunity):
    """
    Run V2 matching, then apply stricter evidence checks.

    The original V2 result is not modified. A new dictionary is returned.
    """
    base = match_capabilities(opportunity)
    result = dict(base)

    title = opportunity.get("title", "")
    product_flag = is_likely_product_purchase(title)
    meaningful_evidence = has_meaningful_technical_evidence(base)

    original_evidence = base.get("matched_evidence") or {}
    result["v2_matched_evidence"] = original_evidence
    result["likely_product_purchase"] = product_flag
    result["meaningful_technical_evidence"] = meaningful_evidence

    flags = list(base.get("review_flags") or [])
    groups = list(base.get("matched_keyword_groups") or [])

    # If a likely product title has only generic evidence, suppress the
    # technical score so generic procurement wording does not inflate fit.
    generic_only_product_match = product_flag and not meaningful_evidence

    if generic_only_product_match:
        result["technical_score"] = 0.0
        result["matched_keyword_groups"] = []
        result["matched_evidence"] = {}
        flags.append(
            "Likely product purchase with no meaningful technical evidence; "
            "generic keyword matches were suppressed."
        )

    # Keep NAICS alignment separate from technical alignment.
    naics_match = bool(result.get("target_naics_match"))
    technical_score = float(result.get("technical_score") or 0.0)

    # Capability score is based only on NAICS and technical fit.
    capability_fit = (40.0 if naics_match else 0.0) + (
        0.60 * technical_score
    )
    capability_fit = round(min(100.0, capability_fit), 1)

    if naics_match and technical_score > 0:
        fit_label = "NAICS and Technical Evidence Match"
        priority = "Review for qualification"
    elif naics_match:
        fit_label = "NAICS Match - Technical Fit Unconfirmed"
        priority = "Investigate scope"
    elif technical_score > 0:
        fit_label = "Technical Evidence Found - NAICS Mismatch"
        priority = "Manual review; verify NAICS relevance"
    else:
        fit_label = "No Confirmed Capability Match"
        priority = "Low priority unless other evidence supports fit"

    if generic_only_product_match:
        fit_label = "Likely Product Purchase - No Meaningful Technical Match"
        priority = "Low priority; review only if product work is relevant"

    result["technical_score"] = round(technical_score, 1)
    result["capability_fit_score"] = capability_fit
    result["fit_label"] = fit_label
    result["preliminary_priority"] = priority
    result["review_flags"] = sorted(set(flags))
    result["matcher_version"] = "V3"

    return result


def main():
    print("=" * 78)
    print("CAPABILITY MATCHER V3")
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

    results = [match_capabilities_v3(row) for row in rows]
    results.sort(
        key=lambda item: (
            item["capability_fit_score"],
            item["technical_score"],
            bool(item["target_naics_match"]),
        ),
        reverse=True,
    )

    print(f"REAL OPPORTUNITIES TESTED: {len(results)}")
    print(
        "TARGET NAICS MATCHES:",
        sum(bool(r.get("target_naics_match")) for r in results),
    )
    print(
        "MEANINGFUL TECHNICAL EVIDENCE:",
        sum(bool(r.get("meaningful_technical_evidence")) for r in results),
    )
    print(
        "LIKELY PRODUCT PURCHASES:",
        sum(bool(r.get("likely_product_purchase")) for r in results),
    )
    print(
        "ZERO TECHNICAL SCORE:",
        sum(float(r.get("technical_score") or 0) == 0 for r in results),
    )

    print("\nTOP 10 BY V3 CAPABILITY FIT")
    for item in results[:10]:
        print(
            json.dumps(
                {
                    "id": item.get("opportunity_id"),
                    "title": item.get("title"),
                    "naics": item.get("naics_code"),
                    "naics_match": item.get("target_naics_match"),
                    "fit": item.get("capability_fit_score"),
                    "technical": item.get("technical_score"),
                    "product_purchase": item.get("likely_product_purchase"),
                    "label": item.get("fit_label"),
                    "priority": item.get("preliminary_priority"),
                    "evidence": item.get("matched_evidence"),
                    "flags": item.get("review_flags"),
                },
                default=str,
            )
        )

    print("\nFIRF OPPORTUNITY CHECK")
    firf_results = [
        item for item in results
        if "FIRF" in str(item.get("title", "")).upper()
    ]

    if firf_results:
        for item in firf_results:
            print(
                json.dumps(
                    {
                        "id": item.get("opportunity_id"),
                        "title": item.get("title"),
                        "naics": item.get("naics_code"),
                        "naics_match": item.get("target_naics_match"),
                        "fit": item.get("capability_fit_score"),
                        "technical": item.get("technical_score"),
                        "eligibility": item.get("eligibility_status"),
                        "label": item.get("fit_label"),
                        "flags": item.get("review_flags"),
                    },
                    default=str,
                )
            )
    else:
        print("No FIRF opportunity found in the real-opportunity query.")

    print("\nCompleted. No database records were changed.")


if __name__ == "__main__":
    main()
