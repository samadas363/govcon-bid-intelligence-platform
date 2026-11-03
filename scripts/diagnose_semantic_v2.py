from src.company_profile import get_company_profile
import pandas as pd

profile = get_company_profile()

print("=" * 70)
print("TTE KEYWORD GROUP STRUCTURE")
print("=" * 70)

groups = profile.get("keyword_groups", {})
print("Type:", type(groups).__name__)

if isinstance(groups, dict):
    for name, terms in groups.items():
        print(f"\nGroup: {name}")
        print("Value type:", type(terms).__name__)
        print("Value:", repr(terms)[:700])

elif isinstance(groups, list):
    for item in groups[:10]:
        print(repr(item)[:700])

print("\n" + "=" * 70)
print("V2 EVIDENCE SUMMARY")
print("=" * 70)

path = "data/reports/semantic_match_v2.csv"
df = pd.read_csv(path)

print("Records:", len(df))
print(
    "Records with direct evidence:",
    (df["direct_evidence_group_count"] > 0).sum()
)
print(
    "Records with target NAICS match:",
    df["target_naics_match"].astype(str).str.lower().eq("true").sum()
)

print("\nRecords with the most direct evidence:")
columns = [
    "opportunity_id",
    "title",
    "naics_code",
    "target_naics_match",
    "semantic_similarity",
    "direct_evidence_groups",
    "direct_evidence_terms",
    "recommendation",
]

print(
    df.sort_values(
        ["direct_evidence_group_count", "semantic_similarity"],
        ascending=[False, False]
    )[columns].head(10).to_string(index=False)
)
