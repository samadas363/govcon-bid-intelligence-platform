import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from database import get_connection

with get_connection() as connection:
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT pg_get_constraintdef(oid)
            FROM pg_constraint
            WHERE conrelid = 'public.opportunities'::regclass
              AND conname = 'opportunities_status_check';
        """)
        row = cursor.fetchone()

        if row:
            print("Allowed status constraint:")
            print(row[0])
        else:
            print("Status constraint was not found.")

print("\nNo database changes were made.")
