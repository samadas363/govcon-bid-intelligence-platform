import csv
import os
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import requests
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")

API_URL = "https://api.sam.gov/opportunities/v2/search"
TIMEOUT = 45
PAGE_SIZE = 100
DATE_RANGE_DAYS = 30
PAUSE_SECONDS = 0.5

TARGET_NAICS = [
    "541330",
    "541611",
    "541614",
    "541990",
    "541715",
    "561320",
]

REPORT_DIR = PROJECT_ROOT / "data" / "reports"
REPORT_FILE = REPORT_DIR / "target_naics_discovery.csv"

FIELDS = [
    "notice_id",
    "solicitation_number",
    "title",
    "agency",
    "notice_type",
    "naics_code",
    "set_aside",
    "posted_date",
    "response_deadline",
    "archive_date",
    "description",
    "source_url",
    "matched_target_naics",
]


def text(value):
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return str(value)
    return " ".join(str(value).split())


def first(record, *keys):
    for key in keys:
        value = record.get(key)
        if value is not None and value != "":
            return value
    return ""


def naics_code(record):
    value = first(record, "naicsCode", "naics", "naics_code")
    if isinstance(value, dict):
        value = first(value, "code", "naicsCode", "value")
    if isinstance(value, list):
        if not value:
            return ""
        item = value[0]
        value = first(item, "code", "naicsCode", "naics", "value") if isinstance(item, dict) else item
    return "".join(c for c in str(value) if c.isdigit())


def notice_key(record):
    notice_id = first(record, "noticeId", "opportunityId", "id")
    if notice_id:
        return "ID:" + text(notice_id).casefold()

    solicitation = first(record, "solicitationNumber", "solicitation_number")
    if solicitation:
        return "SOL:" + text(solicitation).casefold()

    title = text(first(record, "title")).casefold()
    return "TITLE:" + title if title else ""


def convert_record(record, matched_code):
    agency = first(
        record,
        "fullParentPathName",
        "departmentName",
        "agencyName",
        "organizationName",
    )
    set_aside = first(
        record,
        "typeOfSetAsideDescription",
        "typeOfSetAside",
        "setAside",
        "setAsideDescription",
    )
    if isinstance(set_aside, dict):
        set_aside = first(set_aside, "description", "value", "name", "code")

    return {
        "notice_id": text(first(record, "noticeId", "opportunityId", "id")),
        "solicitation_number": text(first(record, "solicitationNumber", "solicitation_number")),
        "title": text(first(record, "title")),
        "agency": text(agency),
        "notice_type": text(first(record, "type", "noticeType", "notice_type")),
        "naics_code": naics_code(record),
        "set_aside": text(set_aside),
        "posted_date": text(first(record, "postedDate", "posted_date")),
        "response_deadline": text(first(record, "responseDeadLine", "responseDeadline", "response_deadline")),
        "archive_date": text(first(record, "archiveDate", "archive_date")),
        "description": text(first(record, "description")),
        "source_url": text(first(record, "uiLink", "sourceUrl", "url", "link")),
        "matched_target_naics": matched_code,
    }


def fetch_page(session, api_key, code, posted_from, posted_to, offset):
    params = {
        "api_key": api_key,
        "postedFrom": posted_from.strftime("%m/%d/%Y"),
        "postedTo": posted_to.strftime("%m/%d/%Y"),
        "ncode": code,
        "limit": PAGE_SIZE,
        "offset": offset,
    }

    try:
        response = session.get(API_URL, params=params, timeout=TIMEOUT)
    except requests.RequestException:
        print(f"ERROR: Network request failed for NAICS {code}.")
        return None

    if response.status_code in (401, 403):
        print("ERROR: SAM.gov rejected the request. Check API-key access.")
        return None

    if response.status_code == 429:
        print("ERROR: SAM.gov rate limit reached. Stop and retry later.")
        return None

    if response.status_code != 200:
        print(f"ERROR: HTTP {response.status_code} for NAICS {code}.")
        print("Response details omitted.")
        return None

    try:
        data = response.json()
    except ValueError:
        print(f"ERROR: Invalid JSON response for NAICS {code}.")
        return None

    if not isinstance(data, dict) or not isinstance(data.get("opportunitiesData", []), list):
        print(f"ERROR: Unexpected response structure for NAICS {code}.")
        return None

    records = data.get("opportunitiesData", [])
    try:
        total = int(data.get("totalRecords", len(records)))
    except (TypeError, ValueError):
        total = len(records)

    return records, total


def discover(api_key, posted_from, posted_to):
    unique = {}
    summary = []

    with requests.Session() as session:
        for code in TARGET_NAICS:
            print(f"\nSearching NAICS {code}...")
            offset = 0
            retrieved = 0
            pages = 0
            total = None
            failed = False

            while True:
                result = fetch_page(
                    session, api_key, code, posted_from, posted_to, offset
                )

                if result is None:
                    failed = True
                    break

                records, total = result
                pages += 1

                if not records:
                    break

                for record in records:
                    if not isinstance(record, dict):
                        continue

                    retrieved += 1
                    key = notice_key(record)
                    if not key:
                        key = f"UNKEYED:{code}:{offset}:{retrieved}"

                    if key not in unique:
                        unique[key] = convert_record(record, code)
                    else:
                        row = unique[key]
                        codes = [v.strip() for v in row["matched_target_naics"].split(",") if v.strip()]
                        if code not in codes:
                            codes.append(code)
                        row["matched_target_naics"] = ", ".join(codes)

                        extra = convert_record(record, code)
                        for field in FIELDS:
                            if field != "matched_target_naics" and not row.get(field) and extra.get(field):
                                row[field] = extra[field]

                print(f"  Page {pages}: {len(records)} records; {retrieved} retrieved.")

                next_offset = offset + len(records)
                if len(records) < PAGE_SIZE or next_offset >= total:
                    break

                offset = next_offset
                time.sleep(PAUSE_SECONDS)

            summary.append({
                "naics": code,
                "reported": total if total is not None else "Unknown",
                "retrieved": retrieved,
                "pages": pages,
                "status": "INCOMPLETE" if failed else "OK",
            })

            if failed:
                print("  Search incomplete; investigate before relying on this report.")
            else:
                print(f"  Search complete: {retrieved} records retrieved.")

            time.sleep(PAUSE_SECONDS)

    return list(unique.values()), summary


def export_csv(records):
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    with REPORT_FILE.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(records)
    return REPORT_FILE


def main():
    api_key = os.getenv("SAM_API_KEY", "").strip()
    if not api_key:
        print("ERROR: SAM_API_KEY is missing from the project .env file.")
        sys.exit(1)

    today = date.today()
    posted_from = today - timedelta(days=DATE_RANGE_DAYS)

    print("=" * 68)
    print("TARGETED SAM.GOV OPPORTUNITY DISCOVERY")
    print("=" * 68)
    print(f"Posting window: {posted_from:%m/%d/%Y} to {today:%m/%d/%Y}")
    print("Database writes: NONE")
    print("Production importer changes: NONE")

    records, summary = discover(api_key, posted_from, today)

    print("\nSEARCH SUMMARY")
    print(f"{'NAICS':<12}{'API total':>14}{'Retrieved':>14}{'Pages':>9}{'Status':>14}")
    print("-" * 63)
    for item in summary:
        print(
            f"{item['naics']:<12}{str(item['reported']):>14}"
            f"{item['retrieved']:>14}{item['pages']:>9}{item['status']:>14}"
        )

    try:
        output = export_csv(records)
    except OSError:
        print("ERROR: Could not write the CSV report.")
        sys.exit(1)

    print("\nREPORT")
    print(f"Unique opportunities exported: {len(records)}")
    print(f"CSV file: {output}")
    print(f"Completed searches: {sum(item['status'] == 'OK' for item in summary)}/{len(summary)}")
    print("PostgreSQL was not modified.")

    if any(item["status"] != "OK" for item in summary):
        print("WARNING: Some NAICS searches were incomplete.")


if __name__ == "__main__":
    main()
