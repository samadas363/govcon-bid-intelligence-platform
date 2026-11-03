import pandas as pd

from src.company_profile import get_company_profile
from src.semantic_matcher_v2 import get_direct_technical_evidence

profile = get_company_profile()
path = "data/reports/semantic_match_v2.csv"
df = pd.read_csv(path)

print("=" * 90)
print("FULL-TEXT DIRECT EVIDENCE ANALYSIS")
print("=" * 90)

print("Records analyzed:", len(df))

if "description" in df.columns:
    print("Description column exists: YES")
else:
    print("Description column exists: NO")

matched_records = []

for _, row in df.iterrows():
    parts = []

    for column in [
        "title",
        "description",
        "opportunity_type",
        "solicitation_number",
        "agency_name",
        "set_aside_type",
        "place_of_performance",
    ]:
        value = row.get(column, "")

        if pd.notna(value) and str(value).strip():
            parts.append(str(value).strip())

    full_text = " ".join(parts)[:8000]

    groups, terms = get_direct_technical_evidence(full_text, profile)

    if groups:
        matched_records.append({
            "opportunity_id": row.get("opportunity_id"),
            "title": row.get("title"),
            "naics_code": row.get("naics_code"),
            "groups": "; ".join(groups),
            "terms": "; ".join(terms),
            "description_length": len(str(row.get("description", ""))),
        })

print("Records with direct evidence:", len(matched_records))

for item in matched_records:
    print("\nOpportunity ID:", item["opportunity_id"])
    print("Title:", item["title"])
    print("NAICS:", item["naics_code"])
    print("Evidence groups:", item["groups"])
    print("Evidence terms:", item["terms"])
    print("Description length:", item["description_length"])

if not matched_records:
    print("\nNo direct evidence found in the report's available text fields.")
    print("This does not rule out relevant evidence in the source records.")

print("\nNo database changes made.")
