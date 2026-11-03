import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.database import get_connection


def main():
    print("=" * 75)
    print("GOVCON BD — PIPELINE MIGRATION DIAGNOSTICS")
    print("=" * 75)

    # Inspect the connection helper without displaying environment variables.
    database_file = PROJECT_ROOT / "src" / "database.py"

    print("\n1. DATABASE CONNECTION IMPLEMENTATION")
    print("-" * 75)

    if database_file.exists():
        source_lines = database_file.read_text(
            encoding="utf-8-sig"
        ).splitlines()

        for number, line in enumerate(source_lines, start=1):
            if (
                "def get_connection" in line
                or "yield " in line
                or "commit(" in line
                or "rollback(" in line
                or "autocommit" in line
                or "psycopg2.connect" in line
                or "contextmanager" in line
            ):
                print(f"{number}: {line.strip()}")
    else:
        print("src/database.py was not found.")

    # Inspect the tables visible through the active connection.
    print("\n2. ALL TABLES IN THE PUBLIC SCHEMA")
    print("-" * 75)

    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT
                    table_name,
                    table_type
                FROM information_schema.tables
                WHERE table_schema = 'public'
                ORDER BY table_name;
            """)

            tables = cursor.fetchall()

            for table_name, table_type in tables:
                print(f"{table_name:<40} {table_type}")

            print(f"\nTotal public tables: {len(tables)}")

            cursor.execute("""
                SELECT
                    schemaname,
                    tablename
                FROM pg_catalog.pg_tables
                WHERE tablename ILIKE '%pipeline%'
                ORDER BY schemaname, tablename;
            """)

            pipeline_tables = cursor.fetchall()

            print("\n3. TABLES WITH 'PIPELINE' IN THEIR NAME")
            print("-" * 75)

            if pipeline_tables:
                for schema, table in pipeline_tables:
                    print(f"{schema}.{table}")
            else:
                print("No pipeline tables found.")

            cursor.execute("""
                SELECT
                    routine_schema,
                    routine_name,
                    routine_type
                FROM information_schema.routines
                WHERE routine_schema = 'public'
                  AND routine_name = 'log_opportunity_pipeline_stage';
            """)

            functions = cursor.fetchall()

            print("\n4. PIPELINE HISTORY FUNCTION")
            print("-" * 75)

            if functions:
                for item in functions:
                    print(item)
            else:
                print("Pipeline history function not found.")

    print("\nDiagnostics complete. No intentional database changes were made.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"DIAGNOSTICS FAILED: {exc}")
        raise
