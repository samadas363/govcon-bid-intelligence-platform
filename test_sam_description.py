
import os

from dotenv import load_dotenv
from src.database import fetch_all
from scripts.import_sam_opportunities import fetch_notice_description

# Load environment variables from .env
load_dotenv()

api_key = os.getenv("SAM_API_KEY")

print("=" * 60)
print("SAM.gov DESCRIPTION RETRIEVAL TEST")
print("=" * 60)

print("API key configured:", bool(api_key))

# Find one real SAM.gov record whose description is an API URL.
query = """
    SELECT title, description
    FROM public.opportunities
    WHERE source_name ILIKE %s
      AND is_sample_data IS FALSE
      AND description LIKE %s
    LIMIT 1
"""

params = ("%SAM%", "%api.sam.gov%noticedesc%")
rows = fetch_all(query, params)

print("Opportunity found:", bool(rows))

if not rows:
    print("No matching opportunity found.")
    print("No database changes were made.")

elif not api_key:
    print("SAM_API_KEY is missing from the environment.")
    print("No database changes were made.")

else:
    title, description_url = rows[0]

    print("Opportunity title:", title)
    print("Testing description endpoint...")

    try:
        description = fetch_notice_description(
            description_url,
            api_key,
        )

        if description:
            print("Description retrieved: True")
            print("\nDescription preview:")
            print(description[:700])
        else:
            print("Description retrieved: False")
            print("The endpoint returned no usable description.")

    except Exception as exc:
        print("Description test failed:", str(exc))

    print("\nNo database changes were made.")

print("=" * 60)