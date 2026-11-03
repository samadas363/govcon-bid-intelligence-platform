"""
GovCon BD Intelligence Platform
Inspect public PostgreSQL tables using the existing database connection.
Read-only operation: no database records or schema are changed.
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.database import get_connection


def main():
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_type = 'BASE TABLE'
                ORDER BY table_name;
                """
            )

            tables = cursor.fetchall()

            print("=" * 60)
            print("GOVCON BD INTELLIGENCE PLATFORM")
            print("DATABASE TABLE INSPECTION")
            print("=" * 60)
            print(f"\nDatabase tables found: {len(tables)}")

            for (table_name,) in tables:
                print(f"- {table_name}")

            print("\nTABLE INSPECTION COMPLETE")
            print("No database records or schema were changed.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"TABLE INSPECTION FAILED: {exc}")
        raise
