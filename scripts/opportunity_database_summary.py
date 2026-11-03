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
                    COUNT(*) AS total,
                    COUNT(*) FILTER (
                        WHERE is_sample_data = FALSE
                    ) AS real_records,
                    COUNT(*) FILTER (
                        WHERE is_sample_data = TRUE
                    ) AS sample_records
                FROM public.opportunities;
            """)

            total, real, samples = cursor.fetchone()

            print("=" * 65)
            print("GOVCON BD — OPPORTUNITY DATABASE SUMMARY")
            print("=" * 65)
            print(f"Total opportunities: {total}")
            print(f"Real opportunities:  {real}")
            print(f"Sample opportunities: {samples}")

            cursor.execute("""
                SELECT
                    COUNT(DISTINCT o.opportunity_id)
                FROM public.opportunities o
                JOIN public.opportunity_scores s
                    ON s.opportunity_id = o.opportunity_id
                WHERE o.is_sample_data = FALSE;
            """)

            scored = cursor.fetchone()[0]
            print(f"Real opportunities with scores: {scored}")
            print(f"Real opportunities without scores: {real - scored}")

            cursor.execute("""
                SELECT
                    COALESCE(o.naics_code, 'Missing') AS naics,
                    COUNT(*) AS record_count,
                    COUNT(*) FILTER (
                        WHERE o.response_deadline IS NULL
                    ) AS missing_deadline,
                    COUNT(*) FILTER (
                        WHERE EXISTS (
                            SELECT 1
                            FROM public.opportunity_scores s
                            WHERE s.opportunity_id = o.opportunity_id
                        )
                    ) AS scored_count
                FROM public.opportunities o
                WHERE o.is_sample_data = FALSE
                GROUP BY COALESCE(o.naics_code, 'Missing')
                ORDER BY record_count DESC, naics;
            """)

            print("\nREAL OPPORTUNITIES BY NAICS")
            print("-" * 65)

            for naics, count, missing_deadline, scored_count in cursor.fetchall():
                print(
                    f"NAICS {naics:<12} "
                    f"Records: {count:<4} "
                    f"No deadline: {missing_deadline:<4} "
                    f"Scored: {scored_count}"
                )

            cursor.execute("""
                SELECT
                    COUNT(*)
                FROM public.opportunity_pipeline;
            """)

            print(f"\nExisting pipeline entries: {cursor.fetchone()[0]}")

    print("\nRead-only diagnostic completed. No data was changed.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"DATABASE SUMMARY FAILED: {exc}")
        raise
