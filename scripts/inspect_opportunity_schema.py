import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from database import get_connection

with get_connection() as connection:
    with connection.cursor() as cursor:
        print("\n=== OPPORTUNITIES TABLE: COLUMNS ===")
        cursor.execute("""
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = 'opportunities'
            ORDER BY ordinal_position;
        """)
        for row in cursor.fetchall():
            print(f"{row[0]} | {row[1]} | nullable={row[2]}")

        print("\n=== UNIQUE CONSTRAINTS ===")
        cursor.execute("""
            SELECT tc.constraint_name, string_agg(kcu.column_name, ', ' ORDER BY kcu.ordinal_position)
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
              ON tc.constraint_name = kcu.constraint_name
             AND tc.table_schema = kcu.table_schema
             AND tc.table_name = kcu.table_name
            WHERE tc.table_schema = 'public'
              AND tc.table_name = 'opportunities'
              AND tc.constraint_type IN ('PRIMARY KEY', 'UNIQUE')
            GROUP BY tc.constraint_name
            ORDER BY tc.constraint_name;
        """)
        rows = cursor.fetchall()
        if rows:
            for row in rows:
                print(f"{row[0]} | {row[1]}")
        else:
            print("No primary-key or unique constraints found.")

        print("\n=== OPPORTUNITIES INDEXES ===")
        cursor.execute("""
            SELECT indexname, indexdef
            FROM pg_indexes
            WHERE schemaname = 'public'
              AND tablename = 'opportunities'
            ORDER BY indexname;
        """)
        for row in cursor.fetchall():
            print(f"{row[0]} | {row[1]}")

        print("\n=== CURRENT RECORD COUNTS ===")
        cursor.execute("""
            SELECT
                COUNT(*) AS total_records,
                COUNT(*) FILTER (WHERE is_sample_data IS TRUE) AS sample_records,
                COUNT(*) FILTER (WHERE is_sample_data IS FALSE) AS real_records,
                COUNT(*) FILTER (WHERE is_sample_data IS NULL) AS unclassified_records
            FROM public.opportunities;
        """)
        counts = cursor.fetchone()
        print(f"Total: {counts[0]}")
        print(f"Sample records: {counts[1]}")
        print(f"Real records: {counts[2]}")
        print(f"Unclassified records: {counts[3]}")

print("\nDATABASE INSPECTION COMPLETE. No records were changed.")
