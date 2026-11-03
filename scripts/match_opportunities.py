import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.database import get_connection


TARGET_NAICS = {
    "561612": "Security Guards and Patrol Services",
    "541512": "Computer Systems Design Services",
    "541690": "Other Scientific and Technical Consulting Services",
    "541618": "Other Management Consulting Services",
}


def classify_opportunity(naics_code):
    if not naics_code:
        return "Needs Review", "NAICS code is missing"

    code = str(naics_code).strip()

    if code in TARGET_NAICS:
        return "Target Match", TARGET_NAICS[code]

    return "Not a Target NAICS", "NAICS does not match target codes"


def main():
    print("\n" + "=" * 72)
    print("GOVCON BD INTELLIGENCE - NAICS OPPORTUNITY MATCHING")
    print("=" * 72)

    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT
                    opportunity_id,
                    title,
                    agency_name,
                    naics_code,
                    posted_date,
                    response_deadline,
                    status,
                    source_url
                FROM public.opportunities
                WHERE is_sample_data = FALSE
                ORDER BY posted_date DESC NULLS LAST, opportunity_id;
            """)

            opportunities = cursor.fetchall()

    if not opportunities:
        print("\nNo real opportunities were found.")
        return

    counts = {
        "Target Match": 0,
        "Needs Review": 0,
        "Not a Target NAICS": 0,
    }

    results = []

    for opportunity in opportunities:
        (
            opportunity_id,
            title,
            agency,
            naics_code,
            posted_date,
            deadline,
            status,
            source_url,
        ) = opportunity

        category, reason = classify_opportunity(naics_code)
        counts[category] += 1

        results.append({
            "id": opportunity_id,
            "title": title,
            "agency": agency,
            "naics": naics_code,
            "posted": posted_date,
            "deadline": deadline,
            "status": status,
            "source_url": source_url,
            "category": category,
            "reason": reason,
        })

    print(f"\nReal opportunities analyzed: {len(results)}")
    print(f"Target NAICS matches:       {counts['Target Match']}")
    print(f"Missing NAICS - review:     {counts['Needs Review']}")
    print(f"Other NAICS codes:          {counts['Not a Target NAICS']}")

    print("\n" + "-" * 72)
    print("TARGET NAICS MATCHES")
    print("-" * 72)

    matches = [r for r in results if r["category"] == "Target Match"]

    if not matches:
        print("No opportunities match the selected target NAICS codes.")
    else:
        for item in matches:
            print(f"\nID: {item['id']} | NAICS: {item['naics']}")
            print(f"Title: {item['title']}")
            print(f"Agency: {item['agency'] or 'Not provided'}")
            print(f"NAICS category: {item['reason']}")
            print(f"Posted: {item['posted'] or 'Not provided'}")
            print(f"Deadline: {item['deadline'] or 'Not provided'}")
            print(f"Current status: {item['status']}")
            print(f"URL: {item['source_url'] or 'Not provided'}")

    print("\n" + "-" * 72)
    print("OPPORTUNITIES NEEDING REVIEW")
    print("-" * 72)

    reviews = [r for r in results if r["category"] == "Needs Review"]

    if not reviews:
        print("No opportunities have missing NAICS codes.")
    else:
        for item in reviews:
            print(
                f"ID: {item['id']} | {item['title']} "
                f"| Agency: {item['agency'] or 'Not provided'}"
            )

    print("\n" + "-" * 72)
    print("TARGET NAICS REFERENCE")
    print("-" * 72)

    for code, description in TARGET_NAICS.items():
        print(f"{code}: {description}")

    print("\nMatching completed. No database records were modified.")


if __name__ == "__main__":
    main()
