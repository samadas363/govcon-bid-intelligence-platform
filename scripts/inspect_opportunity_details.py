import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.database import get_connection


def main():
    query = """
        SELECT
            opportunity_id,
            title,
            agency_name,
            naics_code,
            posted_date,
            response_deadline,
            status,
            LEFT(COALESCE(description, ''), 250) AS description_preview
        FROM public.opportunities
        WHERE is_sample_data = FALSE
        ORDER BY posted_date DESC NULLS LAST
        LIMIT 15;
    """

    print("=" * 80)
    print("GOVCON BD — OPPORTUNITY DATA INSPECTION")
    print("=" * 80)

    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(query)
            rows = cursor.fetchall()

    if not rows:
        print("No real opportunities found.")
        return

    for row in rows:
        (
            opportunity_id,
            title,
            agency,
            naics,
            posted_date,
            deadline,
            status,
            description,
        ) = row

        print(f"\nOpportunity ID: {opportunity_id}")
        print(f"Title: {title or 'Missing'}")
        print(f"Agency: {agency or 'Missing'}")
        print(f"NAICS: {naics or 'Missing'}")
        print(f"Posted date: {posted_date or 'Missing'}")
        print(f"Response deadline: {deadline or 'Missing'}")
        print(f"Database status: {status}")
        print(f"Description preview: {description or 'Missing'}")
        print("-" * 80)

    print(f"\nRecords inspected: {len(rows)}")
    print("Read-only inspection completed. No database changes were made.")


if __name__ == "__main__":
    main()
