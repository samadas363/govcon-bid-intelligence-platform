import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.database import get_connection


def main():
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT
                    current_database(),
                    current_schema(),
                    current_user,
                    inet_server_addr()::text,
                    inet_server_port();
            """)

            database_info = cursor.fetchone()

            print("=" * 70)
            print("DATABASE CONNECTION VERIFICATION")
            print("=" * 70)
            print(f"Database: {database_info[0]}")
            print(f"Schema:   {database_info[1]}")
            print(f"User:     {database_info[2]}")
            print(f"Server:   {database_info[3]}")
            print(f"Port:     {database_info[4]}")

            cursor.execute("""
                SELECT
                    table_schema,
                    table_name,
                    table_type
                FROM information_schema.tables
                WHERE table_name IN (
                    'opportunities',
                    'opportunity_pipeline',
                    'opportunity_pipeline_history'
                )
                ORDER BY table_schema, table_name;
            """)

            print("\nTABLES FOUND")
            print("-" * 70)

            rows = cursor.fetchall()

            if not rows:
                print("None of the three expected tables were found.")
            else:
                for schema, table, table_type in rows:
                    print(f"{schema}.{table} ({table_type})")

    print("\nVerification completed. No database changes were made.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"VERIFICATION FAILED: {exc}")
        raise
