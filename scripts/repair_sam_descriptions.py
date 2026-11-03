"""
GovCon BD Intelligence & Automation Platform
Module: Repair SAM.gov Solicitation Descriptions

Features:
- Repairs empty descriptions and unresolved description URLs.
- Uses the required SAM.gov posting-date search parameters.
- Retries temporary HTTP and network failures.
- Matches notices by solicitation number and notice ID.
- Updates only description and updated_at.
- Protects sample records and existing valid descriptions.
- Does not insert or delete opportunities.
"""

import os
import re
import sys
import time
from datetime import date, datetime, timedelta
from html import unescape
from pathlib import Path

import requests
from dotenv import load_dotenv
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


# ---------------------------------------------------------
# Project configuration
# ---------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.database import fetch_all, execute_query


load_dotenv(PROJECT_ROOT / ".env")

API_KEY = os.getenv("SAM_API_KEY")

SAM_SEARCH_URL = "https://api.sam.gov/opportunities/v2/search"

REQUEST_TIMEOUT = (10, 45)
REQUEST_DELAY_SECONDS = 0.75
MAX_RECORDS_PER_RUN = 100
DATE_WINDOW_DAYS = 7

NOTICE_DESCRIPTION_URL_PATTERN = re.compile(
    r"^https?://(?:api|api-alpha)\.sam\.gov/.*/noticedesc(?:\?.*)?$",
    re.IGNORECASE,
)


# ---------------------------------------------------------
# HTTP session and controlled retries
# ---------------------------------------------------------

def create_session():
    session = requests.Session()

    retry_policy = Retry(
        total=3,
        connect=3,
        read=3,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
        respect_retry_after_header=True,
    )

    adapter = HTTPAdapter(max_retries=retry_policy)

    session.mount("https://", adapter)
    session.mount("http://", adapter)

    return session


SESSION = create_session()


# ---------------------------------------------------------
# Description validation and cleanup
# ---------------------------------------------------------

def is_notice_description_url(value):
    if not isinstance(value, str):
        return False

    return bool(
        NOTICE_DESCRIPTION_URL_PATTERN.match(value.strip())
    )


def clean_description_text(value):
    if not isinstance(value, str):
        return None

    value = unescape(value)

    # Remove scripts and styles.
    value = re.sub(
        r"<(script|style)\b[^>]*>.*?</\1>",
        " ",
        value,
        flags=re.IGNORECASE | re.DOTALL,
    )

    # Preserve paragraph boundaries.
    value = re.sub(
        r"<\s*br\s*/?\s*>",
        "\n",
        value,
        flags=re.IGNORECASE,
    )

    value = re.sub(
        r"</\s*(p|div|li|tr|h[1-6])\s*>",
        "\n",
        value,
        flags=re.IGNORECASE,
    )

    value = re.sub(r"<[^>]+>", " ", value)

    lines = [
        re.sub(r"[ \t]+", " ", line).strip()
        for line in value.splitlines()
    ]

    value = "\n".join(
        line for line in lines if line
    ).strip()

    if not value:
        return None

    if is_notice_description_url(value):
        return None

    if value.lower() in {
        "description",
        "none",
        "null",
        "n/a",
        "not available",
        "description not found",
    }:
        return None

    # Avoid accepting an API error message as the description.
    if value.lower().startswith("error:"):
        return None

    return value


def extract_description_text(payload):
    """
    Extract actual description text from known response structures.
    Do not treat arbitrary JSON as a solicitation description.
    """

    if isinstance(payload, str):
        try:
            import json
            payload = json.loads(payload)
        except (ValueError, TypeError):
            return clean_description_text(payload)

    if not isinstance(payload, dict):
        return None

    # SAM.gov opportunity search responses normally use "description"
    # as a link. Only return it as text if it is not a URL.
    for key in (
        "description",
        "noticeDescription",
        "notice_description",
        "descriptionText",
        "description_text",
    ):
        value = payload.get(key)

        if isinstance(value, str):
            cleaned = clean_description_text(value)

            if cleaned:
                return cleaned

        elif isinstance(value, dict):
            nested = extract_description_text(value)

            if nested:
                return nested

        elif isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    body = item.get("body")

                    if isinstance(body, str):
                        cleaned = clean_description_text(body)

                        if cleaned:
                            return cleaned

    # Support documented-style nested descriptions.
    for key in ("data", "result", "notice", "response"):
        nested = payload.get(key)

        if isinstance(nested, dict):
            result = extract_description_text(nested)

            if result:
                return result

    return None


# ---------------------------------------------------------
# Date handling
# ---------------------------------------------------------

def parse_posted_date(value):
    """
    Convert database date/datetime/string values into a date.
    """

    if isinstance(value, datetime):
        return value.date()

    if isinstance(value, date):
        return value

    if not value:
        return None

    text_value = str(value).strip()

    # Common database and SAM.gov formats.
    for date_format in (
        "%Y-%m-%d",
        "%Y-%m-%d %H:%M:%S",
        "%m/%d/%Y",
    ):
        try:
            return datetime.strptime(
                text_value[:19],
                date_format,
            ).date()
        except ValueError:
            continue

    try:
        return datetime.fromisoformat(
            text_value.replace("Z", "+00:00")
        ).date()
    except ValueError:
        return None


def build_search_date_range(posted_date):
    """
    Return the date range in SAM.gov's required MM/DD/YYYY format.
    Keep the range narrow and within the API's one-year limit.
    """

    start_date = posted_date - timedelta(days=DATE_WINDOW_DAYS)
    end_date = posted_date + timedelta(days=DATE_WINDOW_DAYS)

    today = date.today()

    # Do not search beyond today's date.
    if end_date > today:
        end_date = today

    if start_date > end_date:
        start_date = end_date

    return (
        start_date.strftime("%m/%d/%Y"),
        end_date.strftime("%m/%d/%Y"),
    )


# ---------------------------------------------------------
# Retrieve descriptions
# ---------------------------------------------------------

def fetch_notice_description(description_url):
    """
    Retrieve the description from a stored notice-description URL.
    """

    if not API_KEY:
        return None

    if not is_notice_description_url(description_url):
        return None

    try:
        response = SESSION.get(
            description_url,
            params={"api_key": API_KEY},
            timeout=REQUEST_TIMEOUT,
        )

        if response.status_code != 200:
            print(
                f"    Description endpoint HTTP "
                f"{response.status_code}."
            )
            return None

        content_type = response.headers.get(
            "Content-Type", ""
        ).lower()

        if "json" in content_type:
            try:
                payload = response.json()
            except ValueError:
                print("    Description endpoint returned invalid JSON.")
                return None

            description = extract_description_text(payload)
        else:
            description = clean_description_text(response.text)

        if not description:
            print("    No actual description text was returned.")
            return None

        return description

    except requests.RequestException as exc:
        print(
            "    Description retrieval failed:",
            type(exc).__name__,
        )
        return None


def fetch_description_by_solicitation(record):
    """
    Search SAM.gov using:
    - The solicitation number
    - Required posting date parameters
    - Exact solicitation and notice-ID matching
    """

    solicitation_number = record.get("solicitation_number")
    source_record_id = record.get("source_record_id")
    posted_date = parse_posted_date(record.get("posted_date"))

    if not solicitation_number:
        print("    Cannot search: solicitation number is missing.")
        return None

    if not posted_date:
        print("    Cannot search: posted date is missing or invalid.")
        return None

    posted_from, posted_to = build_search_date_range(posted_date)

    params = {
        "api_key": API_KEY,
        "solnum": solicitation_number.strip(),
        "postedFrom": posted_from,
        "postedTo": posted_to,
        "limit": 100,
        "offset": 0,
    }

    print(
        f"    Searching SAM.gov: "
        f"{posted_from} to {posted_to}"
    )

    try:
        response = SESSION.get(
            SAM_SEARCH_URL,
            params=params,
            timeout=REQUEST_TIMEOUT,
        )

        if response.status_code != 200:
            print(
                f"    SAM.gov search returned HTTP "
                f"{response.status_code}."
            )
            return None

        try:
            payload = response.json()
        except ValueError:
            print("    SAM.gov search returned invalid JSON.")
            return None

    except requests.RequestException as exc:
        print(
            "    SAM.gov search failed:",
            type(exc).__name__,
        )
        return None

    notices = payload.get("opportunitiesData", [])

    if not isinstance(notices, list):
        print("    Unexpected search response structure.")
        return None

    expected_sol = solicitation_number.strip().casefold()
    expected_notice_id = (
        str(source_record_id).strip().casefold()
        if source_record_id
        else None
    )

    # Prefer a result that matches both the solicitation number
    # and the stored SAM.gov notice ID.
    matched_notices = []

    for notice in notices:
        if not isinstance(notice, dict):
            continue

        returned_sol = str(
            notice.get("solicitationNumber") or ""
        ).strip().casefold()

        returned_notice_id = str(
            notice.get("noticeId") or ""
        ).strip().casefold()

        if returned_sol != expected_sol:
            continue

        if (
            expected_notice_id
            and returned_notice_id
            and returned_notice_id != expected_notice_id
        ):
            continue

        matched_notices.append(notice)

    if not matched_notices:
        print(
            "    No exact matching notice was returned "
            "for this solicitation and date range."
        )
        return None

    for notice in matched_notices:
        # First look for actual text.
        description = extract_description_text(notice)

        if description:
            return description

        # Otherwise follow the description URL returned by SAM.gov.
        description_url = notice.get("description")

        if not is_notice_description_url(description_url):
            for key in (
                "descriptionURL",
                "descriptionUrl",
                "noticeDescriptionURL",
            ):
                candidate = notice.get(key)

                if is_notice_description_url(candidate):
                    description_url = candidate
                    break

        if is_notice_description_url(description_url):
            description = fetch_notice_description(
                description_url
            )

            if description:
                return description

    print(
        "    Matching notice found, but no usable "
        "description text was available."
    )

    return None


# ---------------------------------------------------------
# Database selection
# ---------------------------------------------------------

def get_records_needing_repair():
    query = """
        SELECT
            opportunity_id,
            title,
            solicitation_number,
            source_record_id,
            posted_date,
            description
        FROM public.opportunities
        WHERE source_name = %s
          AND is_sample_data IS FALSE
          AND (
              description IS NULL
              OR BTRIM(description) = ''
              OR description LIKE %s
              OR description LIKE %s
          )
        ORDER BY opportunity_id
        LIMIT %s
    """

    return fetch_all(
        query,
        (
            "SAM.gov",
            "%api.sam.gov/%noticedesc%",
            "%api-alpha.sam.gov/%noticedesc%",
            MAX_RECORDS_PER_RUN,
        ),
    )


# ---------------------------------------------------------
# Safe database update
# ---------------------------------------------------------

def update_description(opportunity_id, description):
    """
    Update only the description and timestamp.

    The conditional WHERE clause protects descriptions that another
    process may have repaired since this record was selected.
    """

    query = """
        UPDATE public.opportunities
        SET
            description = %s,
            updated_at = CURRENT_TIMESTAMP
        WHERE opportunity_id = %s
          AND source_name = %s
          AND is_sample_data IS FALSE
          AND (
              description IS NULL
              OR BTRIM(description) = ''
              OR description LIKE %s
              OR description LIKE %s
          )
    """

    return execute_query(
        query,
        (
            description,
            opportunity_id,
            "SAM.gov",
            "%api.sam.gov/%noticedesc%",
            "%api-alpha.sam.gov/%noticedesc%",
        ),
    )


# ---------------------------------------------------------
# Main workflow
# ---------------------------------------------------------

def main():
    print("=" * 65)
    print("SAM.gov SOLICITATION DESCRIPTION REPAIR")
    print("=" * 65)

    if not API_KEY:
        print("ERROR: SAM_API_KEY is not configured.")
        print("Check the .env file in the project root.")
        return 1

    records = get_records_needing_repair()

    if not records:
        print("No records need description repair.")
        return 0

    print(f"Records needing repair: {len(records)}")
    print("Only real SAM.gov records will be processed.")
    print("Sample records are protected.")
    print("Only description and updated_at can be changed.")
    print()

    repaired = 0
    failed = 0
    skipped = 0

    for index, record in enumerate(records, start=1):
        opportunity_id = record["opportunity_id"]
        title = record["title"] or "(untitled)"
        stored_description = record["description"]

        print(
            f"[{index}/{len(records)}] "
            f"Opportunity ID {opportunity_id}: {title}"
        )

        description = None

        # Try the saved API description URL first.
        if is_notice_description_url(stored_description):
            description = fetch_notice_description(
                stored_description
            )

        # If the saved URL fails or description is empty,
        # search using the stored solicitation and posting date.
        if not description:
            description = fetch_description_by_solicitation(
                record
            )

        if not description:
            print("    Unresolved; database record unchanged.")
            failed += 1
            time.sleep(REQUEST_DELAY_SECONDS)
            continue

        try:
            affected_rows = update_description(
                opportunity_id,
                description,
            )

            if affected_rows == 1:
                repaired += 1
                print(
                    "    Description repaired successfully "
                    f"({len(description)} characters)."
                )
            else:
                skipped += 1
                print(
                    "    Update skipped: the record no longer "
                    "matches the repair criteria."
                )

        except Exception as exc:
            failed += 1
            print(
                "    Database update failed:",
                type(exc).__name__,
            )

        time.sleep(REQUEST_DELAY_SECONDS)

    print()
    print("=" * 65)
    print("REPAIR RESULTS")
    print("=" * 65)
    print(f"Records examined: {len(records)}")
    print(f"Descriptions repaired: {repaired}")
    print(f"Retrieval or update failures: {failed}")
    print(f"Records skipped: {skipped}")
    print()
    print("No opportunities were inserted or deleted.")
    print("Sample records were excluded.")
    print("=" * 65)

    return 0


if __name__ == "__main__":
    sys.exit(main())