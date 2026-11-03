import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.database import get_connection


def main():
    query = """
        SELECT
            o.opportunity_id,
            o.title,
            o.agency_name,
            o.naics_code,
            o.posted_date,
            o.response_deadline,
            o.status,
            o.is_sample_data,
            s.total_score,
            s.recommendation
        FROM public.opportunities o
        LEFT JOIN LATERAL (
            SELECT
                os.total_score,
                os.recommendation
            FROM public.opportunity_scores os
            WHERE os.opportunity_id = o.opportunity_id
            ORDER BY os.scored_at DESC
            LIMIT 1
        ) s ON TRUE
        WHERE o.is_sample_data = FALSE
        ORDER BY
            o.response_deadline ASC NULLS LAST,
            o.opportunity_id DESC
        LIMIT 30;
    """

    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(query)
            rows = cursor.fetchall()

    print("=" * 100)
    print("GOVCON BD — REAL OPPORTUNITY REVIEW")
    print("=" * 100)

    if not rows:
        print("No real opportunities found.")
        return

    for row in rows:
        (
            opportunity_id,
            title,
            agency,
            naics,
            posted,
            deadline,
            status,
            is_sample,
            score,
            recommendation,
        ) = row

        print(f"\nOpportunity ID: {opportunity_id}")
        print(f"Title: {title}")
        print(f"Agency: {agency or 'Not provided'}")
        print(f"NAICS: {naics or 'Not provided'}")
        print(f"Posted date: {posted or 'Unknown'}")
        print(f"Response deadline: {deadline or 'Unknown'}")
        print(f"Database status: {status}")
        print(f"Sample record: {is_sample}")
        print(f"Latest score: {score if score is not None else 'Not scored'}")
        print(
            f"Recommendation: "
            f"{recommendation if recommendation else 'Not scored'}"
        )
        print("-" * 80)

    print(f"\nTotal opportunities displayed: {len(rows)}")
    print("Review complete. No database changes were made.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"OPPORTUNITY REVIEW FAILED: {exc}")
        raise
