
import os
import sys
from pathlib import Path
from datetime import date, timedelta

import requests
from dotenv import load_dotenv


# --------------------------------------------------
# Configuration
# --------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")

API_URL = "https://api.sam.gov/opportunities/v2/search"
REQUEST_TIMEOUT = 45
RESULT_LIMIT = 100
DATE_RANGE_DAYS = 30

TARGET_NAICS_CODES = [
    "541330",
    "541611",
    "541614",
    "541990",
    "541715",
    "561320",
]


# --------------------------------------------------
# SAM.gov API search
# --------------------------------------------------

def search_naics(api_key, naics_code, posted_from, posted_to):
    params = {
        "api_key": api_key,
        "postedFrom": posted_from.strftime("%m/%d/%Y"),
        "postedTo": posted_to.strftime("%m/%d/%Y"),
        "ncode": naics_code,
        "limit": RESULT_LIMIT,
        "offset": 0,
    }

    try:
        response = requests.get(
            API_URL,
            params=params,
            timeout=REQUEST_TIMEOUT,
        )

        if response.status_code in (401, 403):
            print("ERROR: SAM.gov rejected the API request.")
            print("Check your API key and its access permissions.")
            return None

        if response.status_code != 200:
            print(f"ERROR: HTTP {response.status_code} for NAICS {naics_code}.")
            print("Response details were omitted.")
            return None

        data = response.json()

        if not isinstance(data, dict):
            print(f"ERROR: Unexpected response for NAICS {naics_code}.")
            return None

        records = data.get("opportunitiesData", [])

        if not isinstance(records, list):
            print(f"ERROR: Unexpected opportunity data for {naics_code}.")
            return None

        return {
            "naics": naics_code,
            "total": data.get("totalRecords", "Unknown"),
            "returned": len(records),
            "records": records,
        }

    except requests.exceptions.Timeout:
        print(f"ERROR: Request timed out for NAICS {naics_code}.")

    except requests.exceptions.RequestException:
        print(f"ERROR: Network request failed for NAICS {naics_code}.")
        print("Sensitive request details were omitted.")

    except (ValueError, TypeError):
        print(f"ERROR: Could not parse the response for NAICS {naics_code}.")

    return None


# --------------------------------------------------
# Main program
# --------------------------------------------------

def main():
    api_key = os.getenv("SAM_API_KEY", "").strip()

    if not api_key:
        print("ERROR: SAM_API_KEY is missing from the project .env file.")
        print("Expected location:", PROJECT_ROOT / ".env")
        sys.exit(1)

    today = date.today()
    posted_from = today - timedelta(days=DATE_RANGE_DAYS)
    posted_to = today

    print("=" * 70)
    print("SAM.GOV TARGET NAICS DISCOVERY TEST")
    print("=" * 70)
    print(f"Posting date range: {posted_from:%m/%d/%Y} to {posted_to:%m/%d/%Y}")
    print(f"NAICS codes: {len(TARGET_NAICS_CODES)}")
    print(f"Maximum records per code: {RESULT_LIMIT}")
    print("Mode: READ ONLY")
    print("Database changes: NONE")
    print()

    results = []

    for naics_code in TARGET_NAICS_CODES:
        print(f"Checking NAICS {naics_code}...")

        result = search_naics(
            api_key,
            naics_code,
            posted_from,
            posted_to,
        )

        if result is None:
            print("  Search unsuccessful.")
            print()
            continue

        results.append(result)

        print(f"  Total matching records: {result['total']}")
        print(f"  Records returned: {result['returned']}")

        for record in result["records"][:3]:
            title = " ".join(
                str(record.get("title") or "Untitled").split()
            )[:110]

            solicitation = record.get("solicitationNumber") or "N/A"
            posted = record.get("postedDate") or "N/A"
            agency = (
                record.get("departmentName")
                or record.get("fullParentPathName")
                or "N/A"
            )

            print(f"    Title: {title}")
            print(f"    Solicitation: {solicitation}")
            print(f"    Posted: {posted}")
            print(f"    Agency: {agency}")

        print()

    print("=" * 70)
    print("DISCOVERY SUMMARY")
    print("=" * 70)
    print(f"{'NAICS':<12}{'Total matches':>20}{'Returned':>15}")
    print("-" * 47)

    for result in results:
        print(
            f"{result['naics']:<12}"
            f"{str(result['total']):>20}"
            f"{result['returned']:>15}"
        )

    print()
    print(f"Successful searches: {len(results)}/{len(TARGET_NAICS_CODES)}")

    failed_codes = [
        code
        for code in TARGET_NAICS_CODES
        if code not in {result["naics"] for result in results}
    ]

    if failed_codes:
        print("Codes needing investigation:", ", ".join(failed_codes))

    print()
    print("Test completed. No database records were changed.")


if __name__ == "__main__":
    main()