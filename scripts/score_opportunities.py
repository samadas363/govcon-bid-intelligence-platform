import sys
from pathlib import Path
from datetime import datetime, timezone
from collections import Counter

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.database import get_connection


# ============================================================
# COMPANY PROFILE: IT / DEVOPS CONSULTING
# ============================================================

TARGET_NAICS = {
    "561612",
    "541512",
    "541690",
    "541618",
}

NAICS_DESCRIPTIONS = {
    "561612": "Security Guards and Patrol Services",
    "541512": "Computer Systems Design Services",
    "541690": "Other Scientific and Technical Consulting Services",
    "541618": "Other Management Consulting Services",
}

# Points are accumulated and capped at 25.
IT_SERVICE_KEYWORDS = {
    "devops": 5,
    "cloud computing": 5,
    "cloud services": 5,
    "cloud infrastructure": 5,
    "cloud migration": 5,
    "cloud": 3,
    "systems integration": 5,
    "system integration": 5,
    "information technology": 4,
    "it consulting": 5,
    "software development": 5,
    "software engineering": 4,
    "application development": 4,
    "automation": 4,
    "infrastructure": 3,
    "database": 3,
    "data analytics": 3,
    "data analysis": 3,
    "cybersecurity": 4,
    "cyber security": 4,
    "network services": 3,
    "technical support": 3,
    "information system": 4,
    "platform engineering": 5,
    "continuous integration": 4,
    "continuous delivery": 4,
    "containerization": 4,
    "kubernetes": 4,
    "migration": 2,
    "managed services": 3,
}

RELEVANT_AGENCY_KEYWORDS = {
    "technology acquisition",
    "information technology",
    "digital service",
    "chief information",
    "defense information systems",
    "cyber",
    "enterprise services",
    "software",
    "technology",
    "information systems",
}


# ============================================================
# HELPERS
# ============================================================

def normalize(value):
    if value is None:
        return ""
    return str(value).strip()


def score_naics(naics_code):
    code = normalize(naics_code)

    if not code:
        return 10, "UNKNOWN", (
            "NAICS is missing. Ten provisional points are assigned, "
            "but the code must be verified before prioritization."
        )

    if code in TARGET_NAICS:
        description = NAICS_DESCRIPTIONS.get(code, "")
        return 30, "MATCH", (
            f"NAICS {code} matches a configured target code"
            + (f" ({description})." if description else ".")
        )

    return 0, "MISMATCH", (
        f"NAICS {code} is outside the configured target codes. "
        "Check the solicitation scope before ruling it out."
    )


def score_service_alignment(title, description):
    title_text = normalize(title).lower()
    description_text = normalize(description).lower()
    text = f"{title_text} {description_text}".strip()

    if not text:
        return 0, "UNKNOWN", [], (
            "Title and description are unavailable. Service alignment "
            "cannot be assessed reliably."
        )

    matched_keywords = []
    raw_points = 0

    for keyword, points in IT_SERVICE_KEYWORDS.items():
        if keyword in text:
            matched_keywords.append(keyword)
            raw_points += points

    score = min(raw_points, 25)

    if matched_keywords:
        evidence = ", ".join(matched_keywords[:10])
        return score, "EVIDENCE_FOUND", matched_keywords, (
            f"Relevant terms found: {evidence}."
        )

    return 0, "NO_MATCH_FOUND", [], (
        "No configured IT/DevOps keywords were found in the available "
        "title and description. This is not proof that the opportunity "
        "is unsuitable; review the full solicitation."
    )


def score_agency(agency_name):
    agency = normalize(agency_name).lower()

    if not agency:
        return 0, "UNKNOWN", "Agency information is missing."

    if any(keyword in agency for keyword in RELEVANT_AGENCY_KEYWORDS):
        return 10, "INDICATOR_FOUND", (
            "Agency name contains a configured technology-related indicator."
        )

    return 5, "IDENTIFIED", (
        "Agency is identified, but its IT buying relevance has not "
        "been independently verified."
    )


def score_deadline(deadline):
    if deadline is None:
        return 7, "UNKNOWN", (
            "Response deadline is missing. Verify the official deadline "
            "and submission instructions."
        )

    if isinstance(deadline, datetime):
        if deadline.tzinfo is None:
            deadline = deadline.replace(tzinfo=timezone.utc)
        deadline_utc = deadline.astimezone(timezone.utc)
    else:
        return 7, "UNKNOWN", (
            "Deadline has an unexpected format. Verify it against the "
            "official solicitation."
        )

    now = datetime.now(timezone.utc)
    days_remaining = (deadline_utc - now).total_seconds() / 86400

    if days_remaining <= 0:
        return 0, "PASSED", (
            "Recorded response deadline has passed. Confirm the official "
            "deadline, including any amendments or extensions."
        )

    if days_remaining > 14:
        return 15, "FEASIBLE", f"Approximately {days_remaining:.1f} days remain."

    if days_remaining >= 8:
        return 12, "FEASIBLE", f"Approximately {days_remaining:.1f} days remain."

    if days_remaining >= 4:
        return 8, "URGENT", f"Approximately {days_remaining:.1f} days remain."

    return 4, "URGENT", (
        f"Only approximately {days_remaining:.1f} days remain. "
        "Check whether a compliant response is feasible."
    )


def score_eligibility(set_aside_type):
    value = normalize(set_aside_type)

    if not value:
        return 5, "UNKNOWN", (
            "Set-aside information is missing. Verify eligibility, "
            "certifications, and any restrictions."
        )

    return 5, "UNVERIFIED", (
        f"Set-aside information is recorded ({value}), but company "
        "eligibility has not been verified."
    )


def score_completeness(title, agency, naics, deadline, description, source_url):
    fields = {
        "title": normalize(title),
        "agency": normalize(agency),
        "NAICS": normalize(naics),
        "deadline": deadline,
        "description": normalize(description),
        "source URL": normalize(source_url),
    }

    populated = sum(bool(value) for value in fields.values())
    total_fields = len(fields)
    score = round((populated / total_fields) * 10)

    missing = [name for name, value in fields.items() if not value]

    if missing:
        note = (
            f"{populated}/{total_fields} key fields populated. "
            f"Missing: {', '.join(missing)}."
        )
    else:
        note = f"All {total_fields} key information fields are populated."

    return score, missing, note


def calculate_confidence(naics, title, description, agency, deadline, source_url):
    """
    Confidence measures the availability of useful screening information.
    It is not a probability of winning a contract.
    """
    checks = [
        bool(normalize(naics)),
        bool(normalize(title)),
        bool(normalize(description)),
        bool(normalize(agency)),
        deadline is not None,
        bool(normalize(source_url)),
    ]

    return round(sum(checks) / len(checks) * 100)


def classify_priority(score, naics_state, service_state, confidence, deadline_state):
    # Missing evidence must not be interpreted as a confirmed no-bid.
    if deadline_state == "PASSED":
        return "Deadline Passed - Verify Immediately"

    if naics_state == "MISMATCH" and service_state == "NO_MATCH_FOUND":
        return "Low Apparent Fit - Manual Review"

    if confidence < 50 or naics_state == "UNKNOWN" or service_state == "UNKNOWN":
        return "Needs More Information"

    if score >= 80:
        return "High Priority - Review Promptly"

    if score >= 60:
        return "Review - Potential Fit"

    if score >= 40:
        return "Further Screening Required"

    return "Low Apparent Fit - Verify Before Deprioritizing"


# ============================================================
# MAIN SCORING PROCESS
# ============================================================

def main():
    print("\n" + "=" * 82)
    print("GOVCON BD INTELLIGENCE - OPPORTUNITY FIT SCORING")
    print("Company profile: IT / DevOps Consulting")
    print("=" * 82)

    print("\nConfigured target NAICS codes:")
    for code in sorted(TARGET_NAICS):
        print(f"  {code}: {NAICS_DESCRIPTIONS.get(code, 'Not defined')}")

    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT
                    opportunity_id,
                    title,
                    agency_name,
                    naics_code,
                    description,
                    set_aside_type,
                    response_deadline,
                    source_url,
                    posted_date,
                    status
                FROM public.opportunities
                WHERE is_sample_data = FALSE
                ORDER BY posted_date DESC NULLS LAST, opportunity_id;
            """)

            opportunities = cursor.fetchall()

    if not opportunities:
        print("\nNo real opportunities found in the database.")
        return

    scored = []

    for row in opportunities:
        (
            opportunity_id,
            title,
            agency,
            naics,
            description,
            set_aside,
            deadline,
            source_url,
            posted_date,
            status,
        ) = row

        naics_points, naics_state, naics_note = score_naics(naics)

        (
            service_points,
            service_state,
            matched_keywords,
            service_note,
        ) = score_service_alignment(title, description)

        agency_points, agency_state, agency_note = score_agency(agency)

        deadline_points, deadline_state, deadline_note = score_deadline(deadline)

        eligibility_points, eligibility_state, eligibility_note = (
            score_eligibility(set_aside)
        )

        completeness_points, missing_fields, completeness_note = (
            score_completeness(
                title,
                agency,
                naics,
                deadline,
                description,
                source_url,
            )
        )

        total = (
            naics_points
            + service_points
            + agency_points
            + deadline_points
            + eligibility_points
            + completeness_points
        )

        confidence = calculate_confidence(
            naics,
            title,
            description,
            agency,
            deadline,
            source_url,
        )

        priority = classify_priority(
            total,
            naics_state,
            service_state,
            confidence,
            deadline_state,
        )

        notes = [
            naics_note,
            service_note,
            agency_note,
            deadline_note,
            eligibility_note,
            completeness_note,
        ]

        scored.append({
            "id": opportunity_id,
            "title": title,
            "agency": agency,
            "naics": naics,
            "deadline": deadline,
            "posted_date": posted_date,
            "status": status,
            "url": source_url,
            "score": total,
            "confidence": confidence,
            "priority": priority,
            "naics_points": naics_points,
            "naics_state": naics_state,
            "service_points": service_points,
            "service_state": service_state,
            "agency_points": agency_points,
            "deadline_points": deadline_points,
            "deadline_state": deadline_state,
            "eligibility_points": eligibility_points,
            "eligibility_state": eligibility_state,
            "completeness_points": completeness_points,
            "missing_fields": missing_fields,
            "matched_keywords": matched_keywords,
            "notes": notes,
        })

    scored.sort(
        key=lambda item: (
            item["priority"] == "High Priority - Review Promptly",
            item["score"],
            item["confidence"],
        ),
        reverse=True,
    )

    print(f"\nReal opportunities assessed: {len(scored)}")
    print("Maximum score: 100 points")
    print("Scoring is preliminary; confidence is a data-completeness indicator.")
    print("No database records, statuses, or sample records were modified.")

    print("\n" + "-" * 82)
    print("TOP OPPORTUNITIES BY SCREENING SCORE")
    print("-" * 82)

    for rank, item in enumerate(scored[:10], start=1):
        print(f"\n{rank}. {normalize(item['title']) or 'Untitled opportunity'}")
        print(f"   Opportunity ID: {item['id']}")
        print(f"   Screening Score: {item['score']}/100")
        print(f"   Information Confidence: {item['confidence']}%")
        print(f"   Recommendation: {item['priority']}")
        print(f"   NAICS: {normalize(item['naics']) or 'MISSING'}")
        print(f"   NAICS assessment: {item['naics_state']}")
        print(f"   Agency: {normalize(item['agency']) or 'Not provided'}")
        print(f"   Posted date: {item['posted_date'] or 'Not provided'}")
        print(f"   Response deadline: {item['deadline'] or 'Not provided'}")
        print(f"   Deadline assessment: {item['deadline_state']}")
        print(f"   Current database status: {item['status']}")
        print(
            "   Factor scores: "
            f"NAICS {item['naics_points']}/30 | "
            f"Services {item['service_points']}/25 | "
            f"Agency {item['agency_points']}/10 | "
            f"Deadline {item['deadline_points']}/15 | "
            f"Eligibility {item['eligibility_points']}/10 | "
            f"Completeness {item['completeness_points']}/10"
        )

        print("   Assessment:")
        for note in item["notes"]:
            print(f"     - {note}")

        print(f"   Source: {item['url'] or 'Not provided'}")

    print("\n" + "-" * 82)
    print("RECOMMENDATION SUMMARY")
    print("-" * 82)

    priority_counts = Counter(item["priority"] for item in scored)

    for priority, count in sorted(priority_counts.items()):
        print(f"{priority}: {count}")

    missing_naics = sum(1 for item in scored if item["naics_state"] == "UNKNOWN")
    service_unknown = sum(
        1 for item in scored if item["service_state"] == "UNKNOWN"
    )
    passed_deadlines = sum(
        1 for item in scored if item["deadline_state"] == "PASSED"
    )

    print("\nDATA QUALITY SUMMARY")
    print(f"Opportunities with missing NAICS: {missing_naics}")
    print(f"Opportunities with insufficient text for service assessment: {service_unknown}")
    print(f"Opportunities with recorded deadlines in the past: {passed_deadlines}")

    print("\n" + "=" * 82)
    print("SCORING COMPLETE")
    print("A high score is not a probability of winning.")
    print("Review the official solicitation, eligibility, scope, and amendments.")
    print("No bid/no-bid decision was automatically made.")
    print("=" * 82)


if __name__ == "__main__":
    main()
