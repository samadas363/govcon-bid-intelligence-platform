"""
TTE Company Profile
GovCon BD Intelligence & Automation Platform

This file stores the initial company profile used by the
Opportunity Qualification Engine.

Important:
- Company information is based on the provided capability statement.
- Certifications must be independently verified.
- No database records are modified by this file.
"""

from copy import deepcopy


COMPANY_PROFILE = {
    # --------------------------------------------------------
    # COMPANY IDENTIFICATION
    # --------------------------------------------------------
    "company_name": "Tiger Team Engineering",
    "abbreviation": "TTE",
    "cage_code": "9LE22",
    "uei": "FNVZL8MEHYT1",
    "website": "https://tigerteameng.com/",

    # --------------------------------------------------------
    # CONTACT INFORMATION FROM THE CAPABILITY STATEMENT
    # --------------------------------------------------------
    "point_of_contact": {
        "name": "Luis Freund",
        "title": "CEO",
        "phone": "(949) 412-7031",
        "email": "lfriend@tte-eng.com",
    },

    # --------------------------------------------------------
    # TARGET NAICS CODES
    # --------------------------------------------------------
    "target_naics_codes": [
        "541330",
        "541611",
        "541614",
        "541990",
        "541715",
        "561320",
    ],

    # --------------------------------------------------------
    # CERTIFICATIONS SHOWN ON THE DOCUMENT
    # These are claims from the capability statement, not
    # independently verified eligibility determinations.
    # --------------------------------------------------------
    "certifications": [
        "SDVOSB",
        "VBE Certified",
    ],

    "certification_verification": {
        "SDVOSB": "Needs independent verification",
        "VBE Certified": "Needs independent verification",
    },

    # --------------------------------------------------------
    # CORE COMPETENCIES
    # --------------------------------------------------------
    "core_competencies": [
        "Engineering Services and Support",
        "Supply Chain Management",
        "Supplier Oversight and Performance",
        "On-Time Delivery",
        "Supplier Base Management",
        "Supplier Quality Management",
        "Visibility and Analytics",
        "Risk Assessment",
        "Continuous Improvement",
        "Logistics Support",
        "Post-Award Procurement Support",
    ],

    # --------------------------------------------------------
    # KEYWORD GROUPS FOR OPPORTUNITY MATCHING
    # These terms support preliminary text matching.
    # They do not prove that TTE meets all solicitation
    # technical requirements.
    # --------------------------------------------------------
    "keyword_groups": {
        "engineering": [
            "engineering services",
            "engineering support",
            "engineering changes",
            "engineering issue mitigation",
            "technical support",
            "engineering research",
        ],

        "supply_chain": [
            "supply chain management",
            "supply chain optimization",
            "supplier management",
            "supplier base management",
            "supplier surveillance",
            "supplier oversight",
            "supplier performance",
            "supplier quality",
        ],

        "procurement": [
            "procurement optimization",
            "procurement support",
            "post-award management",
            "purchasing support",
            "procurement management",
        ],

        "logistics": [
            "logistics support",
            "contractor logistics support",
            "interim contractor logistics support",
            "lifecycle management",
            "critical part prioritization",
            "diminishing manufacturing sources",
            "material shortages",
            "dmsms",
        ],

        "analytics_and_risk": [
            "visibility and analytics",
            "risk assessment",
            "continuous improvement",
            "performance analytics",
            "process improvement",
            "cost reduction",
            "waste reduction",
        ],

        "delivery_and_production": [
            "on-time delivery",
            "delivery improvement",
            "lead-time reduction",
            "production rate",
            "past-due oversight",
            "delivery performance",
        ],

        "staffing": [
            "temporary help services",
            "temporary staffing",
            "staff augmentation",
            "technical personnel",
            "engineering personnel",
        ],

        "management_consulting": [
            "management consulting",
            "business process improvement",
            "operational improvement",
            "program management support",
            "management support",
        ],
    },

    # --------------------------------------------------------
    # PAST PERFORMANCE ORGANIZATIONS LISTED IN THE DOCUMENT
    # These names are not evidence of a specific contract award.
    # --------------------------------------------------------
    "past_performance_organizations": [
        "L3Harris",
        "Boeing",
        "U.S. Marine Corps",
        "Maxar",
    ],

    # --------------------------------------------------------
    # PROJECT EXPERIENCE LISTED IN THE DOCUMENT
    # --------------------------------------------------------
    "project_experience": [
        "Supply Chain Optimization",
        "Supplier Surveillance and Oversight",
        "Procurement Optimization",
        "Diminishing Manufacturing Sources and Material Shortages",
        "Interim Contractor Logistics Support",
        "Lifecycle Management Support",
        "Engineering Support",
    ],

    # --------------------------------------------------------
    # COMPANY-REPORTED DIFFERENTIATORS
    # Figures are reported in the capability statement and
    # have not been independently verified.
    # --------------------------------------------------------
    "reported_differentiators": {
        "on_time_delivery_improvement_percent": 52,
        "lead_time_improvement_percent": 44,
        "cost_and_waste_reduction_percent": 44,
        "production_rate_improvement_percent": 35,
        "procurement_improvement_percent": 48,
    },

    # --------------------------------------------------------
    # QUALIFICATION SETTINGS
    # These are initial system settings, not company facts.
    # Adjust them as the qualification model develops.
    # --------------------------------------------------------
    "qualification_settings": {
        "maximum_score": 100,
        "naics_match_weight": 30,
        "technical_match_weight": 40,
        "deadline_weight": 20,
        "data_completeness_weight": 10,
    },

    # --------------------------------------------------------
    # NOT YET CONFIGURED
    # Do not assume these preferences or eligibility details.
    # --------------------------------------------------------
    "preferences": {
        "geographic_preferences": [],
        "minimum_contract_value": None,
        "maximum_contract_value": None,
        "verified_set_aside_eligibilities": [],
    },
}


def get_company_profile():
    """
    Return a copy of the company profile.

    Returning a copy prevents other modules from accidentally
    modifying the original configuration.
    """
    return deepcopy(COMPANY_PROFILE)


def get_target_naics_codes():
    """Return the configured target NAICS codes."""
    return list(COMPANY_PROFILE["target_naics_codes"])


def get_core_competencies():
    """Return the configured core competencies."""
    return list(COMPANY_PROFILE["core_competencies"])


def get_all_matching_keywords():
    """Return all unique opportunity-matching keywords."""
    keywords = []

    for group_keywords in COMPANY_PROFILE["keyword_groups"].values():
        keywords.extend(group_keywords)

    return sorted(set(keywords))


def validate_company_profile():
    """
    Validate basic configuration fields.

    This checks configuration completeness only.
    It does not verify company registrations or certifications.
    """
    errors = []

    if not COMPANY_PROFILE["company_name"].strip():
        errors.append("Company name is missing.")

    if not COMPANY_PROFILE["target_naics_codes"]:
        errors.append("No target NAICS codes are configured.")

    for code in COMPANY_PROFILE["target_naics_codes"]:
        if not code.isdigit() or len(code) != 6:
            errors.append(f"Invalid NAICS code format: {code}")

    if not COMPANY_PROFILE["core_competencies"]:
        errors.append("No core competencies are configured.")

    settings = COMPANY_PROFILE["qualification_settings"]

    weights = [
        settings["naics_match_weight"],
        settings["technical_match_weight"],
        settings["deadline_weight"],
        settings["data_completeness_weight"],
    ]

    if sum(weights) != settings["maximum_score"]:
        errors.append(
            "Qualification weights must add up to the maximum score."
        )

    return {
        "valid": len(errors) == 0,
        "errors": errors,
    }


if __name__ == "__main__":
    profile = get_company_profile()
    validation = validate_company_profile()

    print("=" * 60)
    print("TTE COMPANY PROFILE")
    print("=" * 60)

    print(f"Company: {profile['company_name']}")
    print(f"CAGE Code: {profile['cage_code']}")
    print(f"UEI: {profile['uei']}")

    print("\nTarget NAICS Codes:")
    for code in get_target_naics_codes():
        print(f"  - {code}")

    print("\nCore Competencies:")
    for competency in get_core_competencies():
        print(f"  - {competency}")

    print("\nMatching Keywords:", len(get_all_matching_keywords()))

    print("\nProfile Validation:")
    print("Valid:", validation["valid"])

    if validation["errors"]:
        for error in validation["errors"]:
            print("ERROR:", error)
    else:
        print("All configuration checks passed.")