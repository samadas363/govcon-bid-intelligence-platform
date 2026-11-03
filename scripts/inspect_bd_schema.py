import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.database import get_connection


def main():
    query = """
        SELECT
            table_name,
            column_name,
            data_type,
            is_nullable
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name IN (
              'opportunities',
              'opportunity_scores',
              'proposals',
              'follow_up_tasks',
              'interactions',
              'debriefs',
              'automation_logs'
          )
        ORDER BY table_name, ordinal_position;
    """

    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(query)
            rows = cursor.fetchall()

    current_table = None

    print("=" * 75)
    print("GOVCON BD — EXISTING BUSINESS DEVELOPMENT SCHEMA")
    print("=" * 75)

    for table_name, column_name, data_type, is_nullable in rows:
        if table_name != current_table:
            current_table = table_name
            print(f"\n[{table_name}]")

        print(
            f"  {column_name:<30} "
            f"{data_type:<22} "
            f"nullable={is_nullable}"
        )

    print("\nSchema inspection complete. No changes were made.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"SCHEMA INSPECTION FAILED: {exc}")
        raise
