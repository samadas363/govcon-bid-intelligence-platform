import os
import csv
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

import requests
from dotenv import load_dotenv

ROOT = Path.cwd()
load_dotenv(ROOT / ".env")

api_key = os.getenv("SAM_API_KEY", "").strip()
if not api_key:
    raise SystemExit("ERROR: SAM_API_KEY is missing from .env")

report_dir = ROOT / "data" / "reports"
reports = sorted(
    report_dir.glob("sam_targeted_discovery_preview_*.csv"),
    key=lambda p: p.stat().st_mtime,
    reverse=True,
)

if not reports:
    raise SystemExit("ERROR: No discovery report found.")

with reports[0].open("r", encoding="utf-8-sig", newline="") as f:
    rows = list(csv.DictReader(f))

if not rows:
    raise SystemExit("ERROR: Discovery report contains no records.")

row = rows[0]
notice_id = (row.get("notice_id") or "").strip()

if not notice_id:
    raise SystemExit("ERROR: First report record has no notice_id.")

endpoint = "https://api.sam.gov/prod/opportunities/v1/noticedesc"

print("SAM.gov DESCRIPTION DIAGNOSTIC")
print("=" * 55)
print("Report:", reports[0].name)
print("Notice ID:", notice_id)
print("Title:", row.get("title", ""))
print("Previous status:", row.get("description_status", ""))
print("Endpoint:", endpoint)
print("API key loaded: YES (value hidden)")
print("\nSending one read-only request...")

try:
    response = requests.get(
        endpoint,
        params={"api_key": api_key, "noticeid": notice_id},
        timeout=(10, 30),
    )

    parts = urlsplit(response.url)
    safe_query = [
        (key, "[REDACTED]" if key.lower() in {"api_key", "apikey"} else value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
    ]
    safe_url = urlunsplit(
        (parts.scheme, parts.netloc, parts.path, urlencode(safe_query), "")
    )

    print("\nHTTP status:", response.status_code)
    print("Final request URL (key redacted):", safe_url)
    print("Content type:", response.headers.get("Content-Type", "unknown"))
    print("Response body preview:")
    print((response.text or "")[:1000])

except requests.RequestException as exc:
    print("Request error:", type(exc).__name__, str(exc))
