"""Explainable capability matching for Tiger Team Engineering.

Read-only matching module. Does not modify database records or the
existing qualification engine.
"""

from __future__ import annotations

import re
from typing import Any

from src.company_profile import COMPANY_PROFILE


def normalize_text(value: Any) -> str:
    """Normalize text for case-insensitive phrase matching."""
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value).lower()).strip()


def normalize_naics(value: Any) -> str:
    """Normalize a NAICS value without changing its meaning."""
    if value is None:
        return ""
    digits = re.sub(r"\D", "", str(value))
    return digits if digits else ""


def get_opportunity_text(opportunity: dict[str, Any]) -> str:
    """Build searchable text from common opportunity fields."""
    fields = (
        "title",
        "description",
        "agency_name",
        "opportunity_type",
        "solicitation_number",
        "place_of_performance",
    )

    return normalize_text(
        " ".join(
            str(opportunity.get(field) or "")
            for field in fields
        )
    )


def get_profile_terms() -> dict[str, list[str]]:
    """Return configured keyword groups and competency phrases."""
    groups = COMPANY_PROFILE.get("keyword_groups", {})
    result: dict[str, list[str]] = {}

    for group_name, terms in groups.items():
        result[group_name] = [
            normalize_text(term)
            for term in terms
            if normalize_text(term)
        ]

    competencies = COMPANY_PROFILE.get("core_competencies", [])
    result["core_competencies"] = [
        normalize_text(term)
        for term in competencies
        if normalize_text(term)
    ]

    return result


def find_phrase_matches(
    text: str,
    phrases: list[str],
) -> list[str]:
    """Find complete phrase matches instead of arbitrary substrings."""
    matches = []

    for phrase in phrases:
        if not phrase:
            continue

        pattern = r"(?<!\w)" + re.escape(phrase) + r"(?!\w)"

        if re.search(pattern, text):
            matches.append(phrase)

    return sorted(set(matches))


def match_capabilities(
    opportunity: dict[str, Any],
) -> dict[str, Any]:
    """Evaluate NAICS and technical alignment with the company profile."""
    text = get_opportunity_text(opportunity)

    target_naics = {
        normalize_naics(code)
        for code in COMPANY_PROFILE.get("target_naics_codes", [])
        if normalize_naics(code)
    }

    opportunity_naics = normalize_naics(
        opportunity.get("naics_code")
    )

    naics_match = bool(
        opportunity_naics and opportunity_naics in target_naics
    )

    term_groups = get_profile_terms()
    matched_groups: dict[str, list[str]] = {}

    for group_name, phrases in term_groups.items():
        matches = find_phrase_matches(text, phrases)
        if matches:
            matched_groups[group_name] = matches

    matched_terms = sorted({
        term
        for matches in matched_groups.values()
        for term in matches
    })

    configured_groups = COMPANY_PROFILE.get("keyword_groups", {})
    group_names = [
        name for name in configured_groups
        if name in term_groups
    ]

    matched_keyword_groups = [
        name for name in group_names
        if matched_groups.get(name)
    ]

    # Each keyword group contributes equally to the technical score.
    # Multiple matches in one group do not inflate its contribution.
    technical_score = (
        100.0 * len(matched_keyword_groups) / len(group_names)
        if group_names
        else 0.0
    )

    competency_matches = matched_groups.get(
        "core_competencies", []
    )

    # Capability fit combines NAICS alignment and technical evidence.
    # Technical evidence is deliberately required for a high fit score.
    naics_fit = 100.0 if naics_match else 0.0
    capability_fit = (
        0.40 * naics_fit
        + 0.60 * technical_score
    )

    if naics_match and matched_keyword_groups:
        fit_label = "Potential Match"
    elif naics_match:
        fit_label = "NAICS Match - Technical Fit Unconfirmed"
    elif matched_keyword_groups:
        fit_label = "Technical Keywords Match - NAICS Mismatch"
    else:
        fit_label = "Low or Unconfirmed Fit"

    return {
        "company_name": COMPANY_PROFILE.get("company_name"),
        "opportunity_naics": opportunity_naics or None,
        "target_naics_match": naics_match,
        "matched_naics": opportunity_naics if naics_match else None,
        "technical_score": round(technical_score, 1),
        "technical_score_maximum": 100,
        "capability_fit_score": round(capability_fit, 1),
        "capability_fit_maximum": 100,
        "fit_label": fit_label,
        "matched_keyword_groups": matched_keyword_groups,
        "matched_terms": matched_terms,
        "matched_core_competencies": competency_matches,
        "review_flags": build_review_flags(
            naics_match=naics_match,
            matched_groups=matched_keyword_groups,
            opportunity=opportunity,
        ),
    }


def build_review_flags(
    naics_match: bool,
    matched_groups: list[str],
    opportunity: dict[str, Any],
) -> list[str]:
    """Explain uncertainties that require human review."""
    flags = []

    if not normalize_naics(opportunity.get("naics_code")):
        flags.append("NAICS code is missing; verify the official notice.")
    elif not naics_match:
        flags.append(
            "Opportunity NAICS is outside TTE's configured target list."
        )

    if not matched_groups:
        flags.append(
            "No configured technical keyword group matched. "
            "Review the full statement of work before rejecting."
        )

    if not normalize_text(opportunity.get("description")):
        flags.append(
            "Description is missing or empty; technical fit is uncertain."
        )

    if not naics_match and not matched_groups:
        flags.append(
            "Low preliminary alignment; deprioritize unless there is "
            "documented scope relevance or a teaming opportunity."
        )

    return flags


def main() -> None:
    print("=" * 72)
    print("TTE CAPABILITY MATCHING ENGINE")
    print("=" * 72)
    print("Company:", COMPANY_PROFILE.get("company_name"))
    print("Target NAICS:", ", ".join(
        COMPANY_PROFILE.get("target_naics_codes", [])
    ))
    print("Core competencies:", len(
        COMPANY_PROFILE.get("core_competencies", [])
    ))
    print("Keyword groups:", len(
        COMPANY_PROFILE.get("keyword_groups", {})
    ))
    print()
    print("Module initialized successfully.")
    print("Database mode: READ ONLY")
    print("No database records were modified.")


if __name__ == "__main__":
    main()
