```python
import sys
from pathlib import Path

# Add the project root to Python's import path.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.database import fetch_all, test_connection


def main():
    print("=" * 60)
    print("GOVCON BD INTELLIGENCE PLATFORM")
    print("DATABASE CONNECTION TEST")
    print("=" * 60)

    # Test the PostgreSQL connection.
    database_info = test_connection()

    print("\nCONNECTION SUCCESSFUL")
    print(f"Database: {database_info['database']}")
    print(f"User: {database_info['user']}")
    print(f"PostgreSQL: {database_info['version']}")

    # Retrieve opportunities from PostgreSQL.
    opportunities = fetch_all(
        """
        SELECT
            external_id,
            title,
            agency,
            naics_code,
            is_sample_data
        FROM opportunities
        ORDER BY external_id;
        """
    )

    print(f"\nOpportunities found: {len(opportunities)}")

    for number, opportunity in enumerate(opportunities, start=1):
        print(f"\nOpportunity {number}")
        print(f"  ID: {opportunity['external_id']}")
        print(f"  Title: {opportunity['title']}")
        print(f"  Agency: {opportunity['agency']}")
        print(f"  NAICS: {opportunity['naics_code']}")
        print(f"  Sample data: {opportunity['is_sample_data']}")

    print("\nDATABASE TEST COMPLETED")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print("\nDATABASE TEST FAILED")
        print(f"Error type: {type(error).__name__}")
        print(f"Error details: {error}")
        sys.exit(1)