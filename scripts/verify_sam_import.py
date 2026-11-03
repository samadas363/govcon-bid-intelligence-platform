import sys
from pathlib import Path

# Add the project root to Python's import path.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.database import get_connection


def main():
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
                    source_name
                FROM public.opportunities
                WHERE is_sample_data = FALSE
                ORDER BY posted_date DESC NULLS LAST
                LIMIT 10;
            """)

            rows = cursor.fetchall()

            print("\n=== LATEST REAL SAM.GOV OPPORTUNITIES ===\n")

            if not rows:
                print("No real opportunities found.")
                return

            for index, row in enumerate(rows, start=1):
                (
                    opportunity_id,
                    title,
                    agency,
                    naics,
                    posted_date,
                    deadline,
                    status,
                    source
                ) = row

                print(f"{index}. {title}")
                print(f"   ID: {opportunity_id}")
                print(f"   Agency: {agency or 'Not provided'}")
                print(f"   NAICS: {naics or 'Not provided'}")
                print(f"   Posted: {posted_date or 'Not provided'}")
                print(f"   Deadline: {deadline or 'Not provided'}")
                print(f"   Status: {status}")
                print(f"   Source: {source}")
                print()

            cursor.execute("""
                SELECT status, COUNT(*)
                FROM public.opportunities
                WHERE is_sample_data = FALSE
                GROUP BY status
                ORDER BY status;
            """)

            print("=== REAL OPPORTUNITIES BY STATUS ===")

            for status, count in cursor.fetchall():
                print(f"{status}: {count}")


if __name__ == "__main__":
    main()
