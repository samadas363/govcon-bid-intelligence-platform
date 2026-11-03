import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.database import get_connection


def main():
    query = """
        SELECT
            tc.table_name,
            tc.constraint_name,
            tc.constraint_type,
            kcu.column_name,
            ccu.table_name AS referenced_table,
            ccu.column_name AS referenced_column
        FROM information_schema.table_constraints tc
        LEFT JOIN information_schema.key_column_usage kcu
            ON tc.constraint_catalog = kcu.constraint_catalog
           AND tc.constraint_schema = kcu.constraint_schema
           AND tc.constraint_name = kcu.constraint_name
           AND tc.table_name = kcu.table_name
        LEFT JOIN information_schema.constraint_column_usage ccu
            ON tc.constraint_catalog = ccu.constraint_catalog
           AND tc.constraint_schema = ccu.constraint_schema
           AND tc.constraint_name = ccu.constraint_name
        WHERE tc.table_schema = 'public'
          AND tc.table_name IN (
              'opportunities',
              'opportunity_scores',
              'proposals',
              'follow_up_tasks',
              'interactions',
              'debriefs'
          )
        ORDER BY tc.table_name, tc.constraint_type, tc.constraint_name;
    """

    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(query)
            rows = cursor.fetchall()

    print("=" * 90)
    print("EXISTING DATABASE CONSTRAINTS")
    print("=" * 90)

    for table, constraint, kind, column, ref_table, ref_column in rows:
        reference = (
            f" -> {ref_table}.{ref_column}"
            if ref_table and ref_column
            else ""
        )
        print(
            f"{table:<25} {kind:<12} {constraint:<45} "
            f"{column or '-'}{reference}"
        )

    print("\nInspection complete. No database changes were made.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"CONSTRAINT INSPECTION FAILED: {exc}")
        raise
