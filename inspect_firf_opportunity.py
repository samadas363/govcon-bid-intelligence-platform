from src.database import get_connection

opportunity_id = 47

query = """
SELECT
    opportunity_id,
    title,
    agency_name,
    opportunity_type,
    naics_code,
    description,
    response_deadline,
    set_aside_type,
    estimated_value,
    source_url,
    status,
    is_sample_data
FROM public.opportunities
WHERE opportunity_id = %s;
"""

with get_connection() as connection:
    with connection.cursor() as cursor:
        cursor.execute(query, (opportunity_id,))
        row = cursor.fetchone()
        columns = [item[0] for item in cursor.description]

if row is None:
    print("Opportunity ID 47 was not found.")
else:
    for column, value in zip(columns, row):
        print(f"\n{column.upper()}:\n{value}")
