import os
import sys
from datetime import date, timedelta
from pathlib import Path

import requests
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")

api_key = os.getenv("SAM_API_KEY", "").strip()

if not api_key:
    print("ERROR: SAM_API_KEY is missing or empty in the project .env file.")
    sys.exit(1)

today = date.today()
start_date = today - timedelta(days=7)

url = "https://api.sam.gov/opportunities/v2/search"

params = {
    "api_key": api_key,
    "postedFrom": start_date.strftime("%m/%d/%Y"),
    "postedTo": today.strftime("%m/%d/%Y"),
    "limit": 1,
    "offset": 0,
}

print("Testing connection to the official SAM.gov API...")
print(f"Posting date range: {params['postedFrom']} to {params['postedTo']}")

try:
    response = requests.get(url, params=params, timeout=30)

    print(f"HTTP status: {response.status_code}")

    if response.status_code == 200:
        try:
            data = response.json()
        except ValueError:
            print("ERROR: SAM.gov responded, but the response was not valid JSON.")
            sys.exit(1)

        opportunities = data.get("opportunitiesData", [])
        total_records = data.get("totalRecords", "Not provided")

        print("SUCCESS: SAM.gov API connection works.")
        print(f"Total matching opportunities: {total_records}")
        print(f"Records returned in this test: {len(opportunities)}")

        if opportunities:
            record = opportunities[0]
            print("\nExample opportunity:")
            print(f"Title: {record.get('title') or 'Not provided'}")
            print(f"Agency: {record.get('department') or 'Not provided'}")
            print(f"NAICS: {record.get('naicsCode') or 'Not provided'}")
            print(f"Posted date: {record.get('postedDate') or 'Not provided'}")

        print("\nNo database changes were made.")

    elif response.status_code == 404:
        print("SAM.gov returned HTTP 404 (no matching data may be available).")
        print("The response alone does not confirm whether the API key is valid.")
        print("No database changes were made.")

    elif response.status_code in (401, 403):
        print("ERROR: SAM.gov rejected the request. Check API-key validity and access.")
        print("Your API key has not been displayed.")
        sys.exit(1)

    else:
        print("ERROR: SAM.gov returned an unexpected HTTP status.")
        print("For security, the response body and API key are not displayed.")
        sys.exit(1)

except requests.exceptions.Timeout:
    print("ERROR: The request timed out. Check your internet connection and retry.")
    sys.exit(1)

except requests.exceptions.RequestException:
    print("ERROR: Could not complete the API request. Check your internet connection.")
    print("Sensitive request details have been hidden.")
    sys.exit(1)
