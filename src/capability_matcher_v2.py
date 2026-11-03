"""Explainable TTE capability matching with synonym and eligibility checks.

This module is read-only and does not modify the database or the
original qualification engine.
"""

from __future__ import annotations

import re
from typing import Any

from src.company_profile import COMPANY_PROFILE


# Transparent synonyms for concepts in TTE's existing profile.
# These terms improve recall; they do not prove that TTE can perform
# every task associated with a matching phrase.
CAPABILITY_SYNONYMS = {
    "engineering": [
        "systems engineering",
        "engineering analysis",
        "engineering services",
        "engineering support",
        "technical support",
        "engineering changes",
        "design engineering",
        "technical engineering",
    ],
    "supply_chain": [
        "supply chain",
        "supply chain management",
        "supply chain optimization",
        "supplier management",
        "supplier performance",
        "supplier quality",
        "supplier oversight",
        "supplier surveillance",
        "supplier base management",
        "vendor management",
        "supplier risk",
    ],
    "procurement": [
        "procurement",
        "procurement support",
        "procurement management",
        "procurement optimization",
        "post-award management",
        "post award management",
        "contract administration",
        "purchasing support",
        "acquisition support",
        "acquisition management",
    ],
    "logistics": [
        "logistics support",
        "contractor logistics support",
        "integrated logistics support",
        "product support",
        "lifecycle management",
        "life cycle management",
        "sustainment support",
        "logistics management",
    ],
    "analytics_and_risk": [
        "risk assessment",
        "risk mitigation",
        "risk management",
        "data analytics",
        "data analysis",
        "performance analytics",
        "performance metrics",
        "management reporting",
        "business intelligence",
        "continuous improvement",
        "visibility and analytics",
    ],
    "delivery_and_production": [
        "on-time delivery",
        "delivery performance",
        "production support",
        "supplier quality assurance",
        "quality assurance",
        "production planning",
        "manufacturing support",
    ],
    "staffing": [
        "staff augmentation",
        "professional staffing",
        "technical staffing",
        "workforce management",
        "personnel support",
    ],
    "management_consulting": [
        "management consulting",
        "management support",
        "business process improvement",
        "operational analysis",
        "process optimization",
        "program management support",
        "organizational management",
    ],
}


def normalize_text(value: Any) -> str:
    """Normalize text for consistent phrase matching."""
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value).lower()).strip()


def normalize_naics(value: Any) -> str:
    """Normalize a NAICS code."""
    if value is None:
        return ""
    digits = re.sub(r"\D", "", str(value))
    return digits or ""


def phrase_matches(text: str, phrases: list[str]) -> list[str]:
    """Match whole phrases, avoiding arbitrary substring matches."""
    matches = []

    for phrase in phrases:
        normalized = normalize_text(phrase)
        if not normalized:
            continue

        pattern = r"(?<!\w)" + re.escape(normalized) + r"(?!\w)"
        if re.search(pattern, text):
            matches.append(normalized)

    return sorted(set(matches))


def opportunity_text(opportunity: dict[str, Any]) -> str:
    """Combine relevant stored fields into searchable text."""
    fields = [
        "title",
        "description",
        "agency_name",
        "opportunity_type",
        "set_aside_type",
        "place_of_performance",
    ]

    return normalize_text(
        " ".join(str(opportunity.get(field) or "") for field in fields)
    )


def check_set_aside(
    opportunity: dict[str, Any],
    text: str,
) -> dict[str, Any]:
    """Flag eligibility requirements without asserting certification."""
    set_aside_value = normalize_text(
        opportunity.get("set_aside_type")
    )

    sdvosb_required = (
        "sdvosb" in set_aside_value
        or "service-disabled veteran-owned" in set_aside_value
        or "service disabled veteran owned" in set_aside_value
        or "service-disabled veteran-owned small business" in text
        or "service disabled veteran owned small business" in text
    )

    profile_checks = COMPANY_PROFILE.get(
        "certification_verification", {}
    )
    sdvosb_status = normalize_text(
        profile_checks.get("SDVOSB", "")
    )

    flags = []

    if sdvosb_required:
        flags.append(
            "SDVOSB set-aside detected. Independently verify current "
            "certification, eligibility, and solicitation requirements."
        )

    if sdvosb_required and (
        "needs independent verification" in sdvosb_status
        or not sdvosb_status
    ):
        eligibility_status = "Verification Required"
    elif sdvosb_required:
        eligibility_status = "Profile Status Requires Human Review"
    else:
        eligibility_status = "No SDVOSB-Only Requirement Detected"

    return {
        "sdvosb_set_aside_detected": sdvosb_required,
        "eligibility_status": eligibility_status,
        "eligibility_flags": flags,
    }


def match_capabilities(
    opportunity: dict[str, Any],
) -> dict[str, Any]:
    """Score capability evidence using the configured TTE profile."""
    text = opportunity_text(opportunity)

    target_codes = {
        normalize_naics(code)
        for code in COMPANY_PROFILE.get("target_naics_codes", [])
        if normalize_naics(code)
    }

    code = normalize_naics(opportunity.get("naics_code"))
    naics_match = bool(code and code in target_codes)

    configured_groups = COMPANY_PROFILE.get("keyword_groups", {})
    matches_by_group: dict[str, list[str]] = {}

    for group_name, original_terms in configured_groups.items():
        synonyms = CAPABILITY_SYNONYMS.get(group_name, [])
        terms = list(original_terms) + synonyms
        matches = phrase_matches(text, terms)

        if matches:
            matches_by_group[group_name] = matches

    total_groups = len(configured_groups)
    matched_groups = len(matches_by_group)

    technical_score = (
        100.0 * matched_groups / total_groups
        if total_groups
        else 0.0
    )

    # Exact NAICS match is evidence of classification alignment only.
    # It is not proof of technical capability or contract eligibility.
    naics_fit = 100.0 if naics_match else 0.0
    capability_fit = 0.40 * naics_fit + 0.60 * technical_score

    text_description = normalize_text(
        opportunity.get("description")
    )
    title = normalize_text(opportunity.get("title"))

    set_aside = check_set_aside(opportunity, text)

    flags = list(set_aside["eligibility_flags"])

    if not code:
        flags.append("NAICS is missing; verify the official notice.")
    elif not naics_match:
        flags.append(
            "NAICS is outside TTE's configured target list."
        )

    if not title:
        flags.append("Opportunity title is missing.")

    if not text_description:
        flags.append(
            "Description is missing; technical fit cannot be assessed."
        )

    if not matches_by_group:
        flags.append(
            "No technical capability phrases matched. Review the "
            "statement of work before rejecting the opportunity."
        )

    if naics_match and not matches_by_group:
        fit_label = "NAICS Match - Technical Fit Unconfirmed"
    elif naics_match and matches_by_group:
        fit_label = "Potential Capability Match - Review Required"
    elif matches_by_group:
        fit_label = "Technical Evidence Found - NAICS Mismatch"
    else:
        fit_label = "Low or Unconfirmed Fit"

    if capability_fit < 20:
        priority = "Low preliminary alignment"
    elif capability_fit < 50:
        priority = "Unconfirmed - investigate scope"
    elif capability_fit < 75:
        priority = "Potential fit - human review"
    else:
        priority = "Stronger preliminary fit - human review"

    return {
        "company_name": COMPANY_PROFILE.get("company_name"),
        "opportunity_id": opportunity.get("opportunity_id"),
        "title": opportunity.get("title"),
        "naics_code": code or None,
        "target_naics_match": naics_match,
        "technical_score": round(technical_score, 1),
        "capability_fit_score": round(capability_fit, 1),
        "matched_keyword_groups": list(matches_by_group),
        "matched_evidence": matches_by_group,
        "fit_label": fit_label,
        "preliminary_priority": priority,
        "sdvosb_set_aside_detected": (
            set_aside["sdvosb_set_aside_detected"]
        ),
        "eligibility_status": set_aside["eligibility_status"],
        "review_flags": flags,
    }


def main() -> None:
    print("=" * 72)
    print("TTE CAPABILITY MATCHER V2")
    print("=" * 72)
    print("Company:", COMPANY_PROFILE.get("company_name"))
    print("Target NAICS codes:", len(
        COMPANY_PROFILE.get("target_naics_codes", [])
    ))
    print("Configured keyword groups:", len(
        COMPANY_PROFILE.get("keyword_groups", {})
    ))
    print("Additional synonym groups:", len(CAPABILITY_SYNONYMS))
    print()
    print("Initialization successful.")
    print("Database mode: READ ONLY")
    print("No database records were modified.")


if __name__ == "__main__":
    main()
