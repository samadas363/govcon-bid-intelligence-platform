import argparse
import csv
import os
import re
import time
import html
from pathlib import Path
from datetime import date, datetime, timedelta
from collections import Counter

import requests
from dotenv import load_dotenv
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = ROOT / "data" / "reports"

API_URL = "https://api.sam.gov/opportunities/v2/search"
DESCRIPTION_URL = "https://api.sam.gov/prod/opportunities/v1/noticedesc"

TARGET_NAICS = [
    "541330",
    "541611",
    "541614",
    "541990",
    "541715",
    "561320",
]

PAGE_SIZE = 100
MAX_PAGES_PER_NAICS = 20
MAX_DESCRIPTION_FETCHES = 300
TIMEOUT = (10, 45)


def create_session():
    session = requests.Session()

    retry = Retry(
        total=3,
        connect=3,
        read=3,
        status=3,
        backoff_factor=1.2,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
        respect_retry_after_header=True,
    )

    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.headers.update({
        "User-Agent": "GovCon-BD-Intelligence-Platform/1.0"
    })

    return session


def text(value):
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return str(value)
    return str(value).strip()


def clean_html(raw):
    raw = html.unescape(raw or "")
    raw = re.sub(
        r"(?is)<(script|style|noscript).*?>.*?</\1>",
        " ",
        raw
    )
    raw = re.sub(
        r"(?i)<br\s*/?>|</p>|</div>|</li>|</tr>",
        "\n",
        raw
    )
    raw = re.sub(r"<[^>]+>", " ", raw)
    raw = raw.replace("\xa0", " ")

    lines = [
        re.sub(r"\s+", " ", line).strip()
        for line in raw.splitlines()
    ]

    return "\n".join(line for line in lines if line).strip()


def extract_description(data, depth=0):
    if depth > 8:
        return ""

    if isinstance(data, str):
        result = clean_html(data)
        if result.startswith(("http://", "https://")):
            return ""
        return result

    if isinstance(data, list):
        results = [
            extract_description(item, depth + 1)
            for item in data
        ]
        return "\n".join(x for x in results if x)

    if not isinstance(data, dict):
        return ""

    preferred = [
        "description",
        "noticeDescription",
        "descriptionText",
        "body",
        "text",
        "content",
    ]

    for key in preferred:
        for actual_key, value in data.items():
            if actual_key.lower() == key.lower():
                result = extract_description(value, depth + 1)
                if result:
                    return result

    for key in [
        "data",
        "result",
        "notice",
        "response",
        "opportunity",
    ]:
        if key in data:
            result = extract_description(data[key], depth + 1)
            if result:
                return result

    return ""


def get_notice_id(record):
    return text(
        record.get("noticeId")
        or record.get("noticeID")
        or record.get("id")
    )


def get_value(record, *keys):
    for key in keys:
        value = record.get(key)
        if value not in (None, ""):
            return value
    return ""


def classify_notice(notice_type):
    value = notice_type.lower()

    if "award" in value:
        return "Award / Generally not an active bid"

    if any(x in value for x in [
        "sources sought",
        "special notice",
        "market research",
    ]):
        return "Market research / Teaming review"

    if "presolicitation" in value or "pre-solicitation" in value:
        return "Upcoming procurement / Monitor"

    if "solicitation" in value:
        return "Potential bid / Evaluate"

    return "Other / Manual review"


def check_deadline(value):
    if not value:
        return "Unknown deadline"

    try:
        parsed = datetime.fromisoformat(
            value.replace("Z", "+00:00")
        ).date()

        days = (parsed - date.today()).days

        if days < 0:
            return "Expired"
        if days == 0:
            return "Due today"
        if days <= 7:
            return "Due within 7 days"
        if days <= 30:
            return "Due within 30 days"

        return "More than 30 days"

    except (ValueError, TypeError):
        return "Unknown deadline"


def fetch_description(session, api_key, record):
    notice_id = get_notice_id(record)

    if not notice_id:
        return "", "Unavailable: no notice ID"

    # Always use the official SAM.gov description endpoint.
    # Do not use description URLs returned by the search response.
    endpoint = DESCRIPTION_URL

    try:
        response = session.get(
            endpoint,
            params={
                "api_key": api_key,
                "noticeid": notice_id,
            },
            timeout=TIMEOUT,
        )

        if response.status_code != 200:
            return "", f"HTTP {response.status_code}"

        try:
            payload = response.json()
            result = extract_description(payload)
        except ValueError:
            result = clean_html(response.text)

        if len(result) >= 20:
            return result, "Fetched"

        return "", "Empty or unrecognized response"

    except requests.RequestException as exc:
        return "", f"Request failed: {type(exc).__name__}"

def get_record_key(record):
    notice_id = get_notice_id(record)

    if notice_id:
        return "ID:" + notice_id

    solicitation = text(
        record.get("solicitationNumber")
    )

    if solicitation:
        return "SOL:" + solicitation.lower()

    title = text(record.get("title")).lower()
    posted = text(record.get("postedDate"))

    return f"TITLE:{title}:{posted}"


def search_naics(session, api_key, naics, start_date, end_date):
    records = []
    offset = 0
    total = None
    pages = 0

    while pages < MAX_PAGES_PER_NAICS:
        params = {
            "api_key": api_key,
            "postedFrom": start_date,
            "postedTo": end_date,
            "ncode": naics,
            "limit": PAGE_SIZE,
            "offset": offset,
        }

        response = session.get(
            API_URL,
            params=params,
            timeout=TIMEOUT,
        )
        response.raise_for_status()

        payload = response.json()
        page_records = payload.get("opportunitiesData", [])

        if total is None:
            total = payload.get("totalRecords")

        if not isinstance(page_records, list):
            break

        records.extend(
            item for item in page_records
            if isinstance(item, dict)
        )

        pages += 1

        print(
            f"  Page {pages}: {len(page_records)} records"
        )

        if len(page_records) < PAGE_SIZE:
            break

        offset += 1

        if total is not None and offset >= int(total):
            break

        time.sleep(0.25)

    return records, total, pages


def transform_record(record, matched_codes, description, description_status):
    notice_type = text(
        get_value(
            record,
            "type",
            "noticeType",
            "notice_type",
        )
    )

    deadline = text(
        get_value(
            record,
            "responseDeadLine",
            "responseDeadline",
        )
    )

    title = text(record.get("title"))

    naics = record.get("naicsCode", "")
    if isinstance(naics, dict):
        naics = naics.get("code", "")

    reasons = []

    if not title:
        reasons.append("Missing title")

    if not description:
        reasons.append("Description unavailable")

    deadline_result = check_deadline(deadline)

    if deadline_result in ["Expired", "Unknown deadline"]:
        reasons.append(deadline_result)

    if "award" in notice_type.lower():
        reasons.append("Award notice")

    classification = classify_notice(notice_type)

    if classification.startswith("Other"):
        reasons.append("Unrecognized notice type")

    agency = text(
        get_value(
            record,
            "fullParentPathName",
            "departmentName",
            "agencyName",
        )
    )

    place = record.get("placeOfPerformance", "")

    if isinstance(place, dict):
        place = ", ".join(
            text(place.get(k))
            for k in ["city", "state", "country"]
            if place.get(k)
        )

    return {
        "notice_id": get_notice_id(record),
        "solicitation_number": text(record.get("solicitationNumber")),
        "title": title,
        "agency": agency,
        "notice_type": notice_type,
        "opportunity_classification": classification,
        "naics_code": text(naics),
        "matched_target_naics": ";".join(sorted(matched_codes)),
        "set_aside": text(
            get_value(
                record,
                "typeOfSetAsideDescription",
                "typeOfSetAside",
            )
        ),
        "posted_date": text(record.get("postedDate")),
        "response_deadline": deadline,
        "deadline_status": deadline_result,
        "archive_date": text(record.get("archiveDate")),
        "description_text": description,
        "description_status": description_status,
        "source_url": text(
            get_value(record, "uiLink", "url")
        ),
        "place_of_performance": text(place),
        "manual_review_reason": "; ".join(reasons),
    }


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--no-descriptions", action="store_true")
    parser.add_argument(
        "--max-descriptions",
        type=int,
        default=MAX_DESCRIPTION_FETCHES,
    )

    args = parser.parse_args()

    if args.days < 1 or args.max_descriptions < 0:
        raise SystemExit("Invalid argument values.")

    load_dotenv(ROOT / ".env")

    api_key = os.getenv("SAM_API_KEY", "").strip()

    if not api_key:
        raise SystemExit(
            "SAM_API_KEY is missing from the project .env file."
        )

    today = date.today()

    posted_from = (
        today - timedelta(days=args.days)
    ).strftime("%m/%d/%Y")

    posted_to = today.strftime("%m/%d/%Y")

    session = create_session()

    all_records = {}
    search_stats = {}

    print("=" * 65)
    print("SAM.GOV TARGETED DISCOVERY V2")
    print("=" * 65)
    print("PostgreSQL connection: NONE")
    print("Database writes: NONE")
    print(f"Date range: {posted_from} to {posted_to}")
    print()

    for naics in TARGET_NAICS:
        print(f"Searching NAICS {naics}...")

        try:
            records, total, pages = search_naics(
                session,
                api_key,
                naics,
                posted_from,
                posted_to,
            )

            search_stats[naics] = {
                "retrieved": len(records),
                "total": total,
                "pages": pages,
            }

            for record in records:
                key = get_record_key(record)

                if key not in all_records:
                    all_records[key] = {
                        "record": record,
                        "codes": {naics},
                    }
                else:
                    all_records[key]["codes"].add(naics)

            print(
                f"  Retrieved: {len(records)} | "
                f"API total: {total} | Pages: {pages}"
            )

        except requests.RequestException as exc:
            print(
                f"  API ERROR for {naics}: "
                f"{type(exc).__name__}"
            )
            search_stats[naics] = {
                "retrieved": 0,
                "total": None,
                "pages": 0,
            }

        time.sleep(0.3)

    print()
    print(f"Unique notices: {len(all_records)}")

    rows = []
    description_attempts = 0
    description_successes = 0

    for item in all_records.values():
        record = item["record"]

        description = ""
        description_status = "Not fetched"

        raw_description = text(record.get("description"))

        if raw_description and "noticedesc" not in raw_description.lower():
            description = clean_html(raw_description)
            if len(description) >= 20:
                description_status = "Available in search response"

        if (
            not args.no_descriptions
            and not description
            and description_attempts < args.max_descriptions
        ):
            description_attempts += 1

            description, description_status = fetch_description(
                session,
                api_key,
                record,
            )

            if description:
                description_successes += 1

            time.sleep(0.1)

        elif not description and not args.no_descriptions:
            description_status = "Skipped: fetch limit reached"

        rows.append(
            transform_record(
                record,
                item["codes"],
                description,
                description_status,
            )
        )

    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    output_file = REPORT_DIR / (
        f"sam_targeted_discovery_preview_{timestamp}.csv"
    )

    columns = list(rows[0].keys()) if rows else [
        "notice_id",
        "solicitation_number",
        "title",
        "agency",
        "notice_type",
        "opportunity_classification",
        "naics_code",
        "matched_target_naics",
        "set_aside",
        "posted_date",
        "response_deadline",
        "deadline_status",
        "archive_date",
        "description_text",
        "description_status",
        "source_url",
        "place_of_performance",
        "manual_review_reason",
    ]

    with output_file.open(
        "w",
        newline="",
        encoding="utf-8-sig",
    ) as file:
        writer = csv.DictWriter(file, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)

    print()
    print("=" * 65)
    print("DISCOVERY RESULTS")
    print("=" * 65)

    print(f"Unique opportunities: {len(rows)}")
    print(f"Description attempts: {description_attempts}")
    print(f"Descriptions retrieved: {description_successes}")

    print("\nClassification:")
    for name, count in Counter(
        row["opportunity_classification"] for row in rows
    ).most_common():
        print(f"  {name}: {count}")

    print("\nDeadline status:")
    for name, count in Counter(
        row["deadline_status"] for row in rows
    ).most_common():
        print(f"  {name}: {count}")

    print("\nNAICS search results:")
    for code, stats in search_stats.items():
        print(
            f"  {code}: {stats['retrieved']} retrieved; "
            f"API total: {stats['total']}; "
            f"pages: {stats['pages']}"
        )

    print(f"\nReport saved: {output_file}")
    print("PostgreSQL was not accessed.")


if __name__ == "__main__":
    main()


