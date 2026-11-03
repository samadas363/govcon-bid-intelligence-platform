"""
GovCon BD Intelligence Platform
PostgreSQL connection and opportunities test.
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.database import get_connection


def main():
    try:
        # get_connection() is a context manager.
        with get_connection() as connection:

            print("=" * 60)
            print("GOVCON BD INTELLIGENCE PLATFORM")
            print("=" * 60)

            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT
                        current_user,
                        current_database(),
                        version();
                    """
                )

                user, database, version = cursor.fetchone()

                print("\nCONNECTION SUCCESSFUL")
                print(f"User: {user}")
                print(f"Database: {database}")
                print(f"PostgreSQL: {version}")

                cursor.execute(
                    """
                    SELECT
                        opportunity_id,
                        source_name,
                        source_record_id,
                        solicitation_number,
                        title,
                        agency_name,
                        opportunity_type,
                        naics_code,
                        set_aside_type,
                        response_deadline,
                        status,
                        is_sample_data
                    FROM public.opportunities
                    ORDER BY opportunity_id;
                    """
                )

                opportunities = cursor.fetchall()

                print("\n" + "=" * 60)
                print(f"OPPORTUNITIES FOUND: {len(opportunities)}")
                print("=" * 60)

                for row in opportunities:
                    (
                        opportunity_id,
                        source_name,
                        source_record_id,
                        solicitation_number,
                        title,
                        agency_name,
                        opportunity_type,
                        naics_code,
                        set_aside_type,
                        response_deadline,
                        status,
                        is_sample_data,
                    ) = row

                    print(f"\nID: {opportunity_id}")
                    print(f"Title: {title}")
                    print(f"Agency: {agency_name}")
                    print(f"Source: {source_name}")
                    print(f"Source Record ID: {source_record_id}")
                    print(f"Solicitation Number: {solicitation_number}")
                    print(f"Opportunity Type: {opportunity_type}")
                    print(f"NAICS Code: {naics_code}")
                    print(f"Set-Aside: {set_aside_type}")
                    print(f"Response Deadline: {response_deadline}")
                    print(f"Status: {status}")
                    print(f"Sample Data: {is_sample_data}")
                    print("-" * 60)

                cursor.execute(
                    """
                    SELECT
                        is_sample_data,
                        COUNT(*)
                    FROM public.opportunities
                    GROUP BY is_sample_data
                    ORDER BY is_sample_data;
                    """
                )

                summary = cursor.fetchall()

                print("\nOPPORTUNITY SUMMARY")
                print("-" * 60)

                for is_sample, count in summary:
                    label = (
                        "Sample records"
                        if is_sample
                        else "Non-sample records"
                    )
                    print(f"{label}: {count}")

        print("\nDATABASE TEST PASSED")
        print("Connection and opportunity query succeeded.")
        return True

    except Exception as error:
        print("\nDATABASE TEST FAILED")
        print(f"Error type: {type(error).__name__}")
        print(f"Error details: {error}")
        return False


if __name__ == "__main__":
    success = main()

    if not success:
        sys.exit(1)
