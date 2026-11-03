import os
import re
import sys
from datetime import date, datetime, timedelta, timezone
from html import unescape
from pathlib import Path
from urllib.parse import urlparse

import requests
from dotenv import load_dotenv

# ============================================================
# PROJECT CONFIGURATION
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))
load_dotenv(PROJECT_ROOT / ".env")

from database import get_connection

API_URL = "https://api.sam.gov/opportunities/v2/search"
SOURCE_NAME = "SAM.gov"

IMPORT_LIMIT = 25
DATE_RANGE_DAYS = 7
INITIAL_STATUS = "New"
REQUEST_TIMEOUT = 30


# ============================================================
# TEXT AND DATE HELPERS
# ============================================================

def clean_text(value):
    """Return cleaned text or None for empty values."""
    if value is None:
        return None

    value = str(value).strip()

    if not value or value.lower() in {
        "null",
        "none",
        "n/a",
    }:
        return None

    return value


def parse_posted_date(value):
    """Convert SAM.gov posted date to a Python date."""
    value = clean_text(value)

    if not value:
        return None

    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def parse_deadline(value):
    """Convert SAM.gov response deadline to a datetime."""
    value = clean_text(value)

    if not value:
        return None

    try:
        parsed = datetime.fromisoformat(
            value.replace("Z", "+00:00")
        )

        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)

        return parsed

    except ValueError:
        return None


# ============================================================
# OPPORTUNITY FIELD HELPERS
# ============================================================

def build_place_of_performance(record):
    """Build a readable place-of-performance string."""
    place = record.get("placeOfPerformance")

    if not isinstance(place, dict):
        return None

    parts = []

    for key in ("city", "state", "zip"):
        value = place.get(key)

        if isinstance(value, dict):
            value = value.get("name") or value.get("code")

        value = clean_text(value)

        if value:
            parts.append(value)

    country = place.get("country")

    if isinstance(country, dict):
        country_name = clean_text(
            country.get("name") or country.get("code")
        )

        if country_name:
            parts.append(country_name)

    return ", ".join(parts) if parts else None


def get_agency(record):
    """Build the agency hierarchy."""
    full_path = clean_text(
        record.get("fullParentPathName")
    )

    if full_path:
        return full_path.replace(".", " > ")

    parts = [
        clean_text(record.get("department")),
        clean_text(record.get("subTier")),
        clean_text(record.get("office")),
    ]

    return " > ".join(
        part for part in parts if part
    ) or None


# ============================================================
# SAM.GOV DESCRIPTION HELPERS
# ============================================================

def is_notice_description_url(value):
    """
    Detect a SAM.gov notice-description API URL.

    Such a URL is not the actual solicitation description.
    """
    value = clean_text(value)

    if not value:
        return False

    parsed = urlparse(value)

    return (
        parsed.scheme in {"http", "https"}
        and parsed.netloc.lower()
        in {
            "api.sam.gov",
            "api-alpha.sam.gov",
        }
        and "noticedesc" in parsed.path.lower()
    )


def extract_description_text(payload):
    """
    Extract readable text from common notice-description
    response formats, including JSON, plain text, and HTML.
    """
    if isinstance(payload, dict):

        # Check common description-body field names first.
        preferred_keys = (
            "description",
            "body",
            "descriptionText",
            "noticeDescription",
            "text",
        )

        for key in preferred_keys:
            value = payload.get(key)

            if isinstance(value, str):
                if (
                    value.strip()
                    and not is_notice_description_url(value)
                ):
                    return extract_description_text(value)

            elif isinstance(value, (dict, list)):
                result = extract_description_text(value)

                if result:
                    return result

        # Handle common wrapper objects.
        wrapper_keys = (
            "data",
            "notice",
            "result",
            "response",
            "descriptionBody",
        )

        for key in wrapper_keys:
            value = payload.get(key)

            if isinstance(value, (dict, list, str)):
                result = extract_description_text(value)

                if result:
                    return result

        return None

    if isinstance(payload, list):
        for item in payload:
            result = extract_description_text(item)

            if result:
                return result

        return None

    if not isinstance(payload, str):
        return None

    text = payload.strip()

    if not text:
        return None

    # Handle JSON returned as a text string.
    if text.startswith("{") or text.startswith("["):
        try:
            import json

            decoded = json.loads(text)

            if isinstance(decoded, (dict, list)):
                result = extract_description_text(decoded)

                if result:
                    return result

        except (ValueError, TypeError):
            pass

    # Remove scripts and styles from HTML.
    text = re.sub(
        r"(?is)<(script|style)\b.*?>.*?</\1>",
        " ",
        text,
    )

    # Preserve paragraph boundaries.
    text = re.sub(
        r"(?s)<br\s*/?>|</p\s*>|</div\s*>|</li\s*>",
        "\n",
        text,
    )

    # Remove remaining HTML tags.
    text = re.sub(r"(?s)<[^>]+>", " ", text)

    # Decode HTML entities.
    text = unescape(text)

    # Normalize whitespace.
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text)

    text = text.strip()

    return text or None


def fetch_notice_description(description_url, api_key):
    """
    Retrieve the actual notice description from a SAM.gov
    description endpoint when the endpoint is available.

    Returns None if the request fails or the response does
    not contain usable description text.
    """
    if not is_notice_description_url(description_url):
        return clean_text(description_url)

    try:
        response = requests.get(
            description_url,
            params={"api_key": api_key},
            timeout=REQUEST_TIMEOUT,
        )

        if response.status_code != 200:
            print(
                "  Description unavailable "
                f"(HTTP {response.status_code})."
            )

            return None

        content_type = response.headers.get(
            "Content-Type",
            "",
        ).lower()

        if "json" in content_type:
            try:
                body = extract_description_text(
                    response.json()
                )

            except ValueError:
                body = extract_description_text(
                    response.text
                )

        else:
            body = extract_description_text(
                response.text
            )

        if not body:
            print(
                "  No usable description text returned."
            )

            return None

        # Never accept the endpoint URL itself as body text.
        if is_notice_description_url(body):
            print(
                "  Description response contained a URL "
                "instead of description text."
            )

            return None

        return body

    except requests.exceptions.RequestException:
        print(
            "  Description request failed. "
            "Continuing with the remaining opportunities."
        )

        return None


# ============================================================
# MAP SAM.GOV RECORD TO DATABASE FIELDS
# ============================================================

def map_opportunity(record):
    """Convert a SAM.gov record to the database structure."""
    notice_id = clean_text(record.get("noticeId"))
    title = clean_text(record.get("title"))

    if not notice_id or not title:
        return None

    description = clean_text(
        record.get("_resolved_description")
    )

    if not description:
        raw_description = clean_text(
            record.get("description")
        )

        # Reject API URLs in the description field.
        if (
            raw_description
            and not is_notice_description_url(
                raw_description
            )
        ):
            description = raw_description

    return {
        "source_name": SOURCE_NAME,
        "source_record_id": notice_id,

        "solicitation_number": clean_text(
            record.get("solicitationNumber")
        ),

        "title": title,

        "agency_name": get_agency(record),

        "opportunity_type": clean_text(
            record.get("type")
        ),

        "description": description,

        "naics_code": clean_text(
            record.get("naicsCode")
        ),

        "set_aside_type": (
            clean_text(
                record.get("typeOfSetAsideDescription")
            )
            or clean_text(
                record.get("typeOfSetAside")
            )
        ),

        "place_of_performance": (
            build_place_of_performance(record)
        ),

        "estimated_value": None,

        "posted_date": parse_posted_date(
            record.get("postedDate")
        ),

        "response_deadline": parse_deadline(
            record.get("responseDeadLine")
        ),

        "status": INITIAL_STATUS,

        "source_url": (
            clean_text(record.get("uiLink"))
            or clean_text(
                record.get("additionalInfoLink")
            )
        ),

        "is_sample_data": False,
    }


# ============================================================
# FETCH OPPORTUNITIES FROM SAM.GOV
# ============================================================

def fetch_opportunities(api_key):
    """Fetch recent opportunities and resolve description URLs."""
    today = date.today()

    posted_from = today - timedelta(
        days=DATE_RANGE_DAYS
    )

    params = {
        "api_key": api_key,
        "postedFrom": posted_from.strftime("%m/%d/%Y"),
        "postedTo": today.strftime("%m/%d/%Y"),
        "limit": IMPORT_LIMIT,
        "offset": 0,
    }

    print("Requesting opportunities from SAM.gov...")

    print(
        f"Posted date range: "
        f"{params['postedFrom']} to {params['postedTo']}"
    )

    print(
        f"Maximum records requested: {IMPORT_LIMIT}"
    )

    response = requests.get(
        API_URL,
        params=params,
        timeout=60,
    )

    if response.status_code in (401, 403):
        raise RuntimeError(
            "SAM.gov rejected the request. "
            "Check API-key validity and access."
        )

    if response.status_code != 200:
        raise RuntimeError(
            f"SAM.gov returned HTTP {response.status_code}. "
            "Response details are hidden to protect credentials."
        )

    data = response.json()

    records = data.get("opportunitiesData", [])

    if not isinstance(records, list):
        raise RuntimeError(
            "Unexpected SAM.gov response: "
            "opportunitiesData is not a list."
        )

    print(
        "Total matching opportunities reported: "
        f"{data.get('totalRecords', 'Unknown')}"
    )

    print(f"Records returned: {len(records)}")

    attempted = 0
    resolved = 0

    for index, record in enumerate(
        records,
        start=1,
    ):
        if not isinstance(record, dict):
            continue

        raw_description = clean_text(
            record.get("description")
        )

        if (
            raw_description
            and is_notice_description_url(
                raw_description
            )
        ):
            attempted += 1

            print(
                f"Resolving notice description "
                f"{attempted} "
                f"(record {index}/{len(records)})..."
            )

            record["_resolved_description"] = (
                fetch_notice_description(
                    raw_description,
                    api_key,
                )
            )

            if record["_resolved_description"]:
                resolved += 1

        else:
            record["_resolved_description"] = (
                raw_description
            )

    print(
        "Notice descriptions resolved: "
        f"{resolved}/{attempted} URL-based descriptions"
    )

    return records


# ============================================================
# IMPORT INTO POSTGRESQL
# ============================================================

def import_opportunities(records):
    """
    Insert or refresh real opportunities.

    Existing sample records are protected.
    A missing description from the API will not overwrite
    a valid existing description.
    """
    insert_sql = """
        INSERT INTO public.opportunities (
            source_name,
            source_record_id,
            solicitation_number,
            title,
            agency_name,
            opportunity_type,
            description,
            naics_code,
            set_aside_type,
            place_of_performance,
            estimated_value,
            posted_date,
            response_deadline,
            status,
            source_url,
            is_sample_data
        )
        VALUES (
            %(source_name)s,
            %(source_record_id)s,
            %(solicitation_number)s,
            %(title)s,
            %(agency_name)s,
            %(opportunity_type)s,
            %(description)s,
            %(naics_code)s,
            %(set_aside_type)s,
            %(place_of_performance)s,
            %(estimated_value)s,
            %(posted_date)s,
            %(response_deadline)s,
            %(status)s,
            %(source_url)s,
            %(is_sample_data)s
        )
        ON CONFLICT (source_name, source_record_id)
        DO UPDATE SET
            solicitation_number = EXCLUDED.solicitation_number,
            title = EXCLUDED.title,
            agency_name = EXCLUDED.agency_name,
            opportunity_type = EXCLUDED.opportunity_type,

            description = CASE
                WHEN EXCLUDED.description IS NOT NULL
                     AND EXCLUDED.description
                         !~* '^https?://api(-alpha)?[.]sam[.]gov/.*/noticedesc[?]'
                    THEN EXCLUDED.description

                WHEN public.opportunities.description
                         ~* '^https?://api(-alpha)?[.]sam[.]gov/.*/noticedesc[?]'
                    THEN NULL

                ELSE public.opportunities.description
            END,

            naics_code = EXCLUDED.naics_code,
            set_aside_type = EXCLUDED.set_aside_type,
            place_of_performance = EXCLUDED.place_of_performance,
            posted_date = EXCLUDED.posted_date,
            response_deadline = EXCLUDED.response_deadline,

            source_url = COALESCE(
                EXCLUDED.source_url,
                public.opportunities.source_url
            ),

            updated_at = CURRENT_TIMESTAMP

        WHERE public.opportunities.is_sample_data IS FALSE

        RETURNING opportunity_id;
    """

    inserted_or_updated = 0
    skipped_invalid = 0
    protected_sample_conflicts = 0

    with get_connection() as connection:
        try:
            with connection.cursor() as cursor:

                for record in records:
                    opportunity = map_opportunity(
                        record
                    )

                    if opportunity is None:
                        skipped_invalid += 1
                        continue

                    cursor.execute(
                        insert_sql,
                        opportunity,
                    )

                    result = cursor.fetchone()

                    if result:
                        inserted_or_updated += 1
                    else:
                        protected_sample_conflicts += 1

                cursor.execute("""
                    SELECT
                        COUNT(*),

                        COUNT(*) FILTER (
                            WHERE is_sample_data IS TRUE
                        ),

                        COUNT(*) FILTER (
                            WHERE is_sample_data IS FALSE
                        ),

                        COUNT(*) FILTER (
                            WHERE source_name = 'SAM.gov'
                              AND is_sample_data IS FALSE
                        )

                    FROM public.opportunities;
                """)

                (
                    total,
                    samples,
                    real_records,
                    sam_records,
                ) = cursor.fetchone()

            connection.commit()

        except Exception:
            connection.rollback()
            raise

    print("\n=== IMPORT RESULTS ===")

    print(
        "New or refreshed real records: "
        f"{inserted_or_updated}"
    )

    print(
        f"Skipped invalid records: {skipped_invalid}"
    )

    print(
        "Protected sample-data conflicts: "
        f"{protected_sample_conflicts}"
    )

    print(
        f"Total opportunities in database: {total}"
    )

    print(
        f"Sample records preserved: {samples}"
    )

    print(
        f"Real records in database: {real_records}"
    )

    print(
        "Real SAM.gov records in database: "
        f"{sam_records}"
    )

    print(
        "\nImport transaction completed successfully."
    )


# ============================================================
# MAIN
# ============================================================

def main():
    api_key = os.getenv(
        "SAM_API_KEY",
        "",
    ).strip()

    if not api_key:
        print(
            "ERROR: SAM_API_KEY is missing "
            "from the project .env file."
        )

        sys.exit(1)

    try:
        records = fetch_opportunities(api_key)

        if not records:
            print(
                "No opportunities returned. "
                "Database was not changed."
            )

            return

        import_opportunities(records)

    except requests.exceptions.Timeout:
        print("ERROR: SAM.gov request timed out.")
        sys.exit(1)

    except requests.exceptions.RequestException:
        print(
            "ERROR: SAM.gov network request failed. "
            "Sensitive details hidden."
        )

        sys.exit(1)

    except Exception as exc:
        print(
            f"ERROR: Import failed: "
            f"{type(exc).__name__}: {exc}"
        )

        print("Review the error before retrying.")

        sys.exit(1)


if __name__ == "__main__":
    main()
