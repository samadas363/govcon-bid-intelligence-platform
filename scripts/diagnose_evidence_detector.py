import pandas as pd

from src.company_profile import get_company_profile
from src.semantic_matcher_v2 import get_direct_technical_evidence

profile = get_company_profile()

print("=" * 70)
print("DIRECT EVIDENCE DETECTOR DIAGNOSTIC")
print("=" * 70)

# Test 1: A phrase taken directly from TTE's profile
test_text = (
    "The contractor provides supplier surveillance, "
    "supplier oversight, and supply chain management."
)

groups, terms = get_direct_technical_evidence(test_text, profile)

print("\nTEST 1: Known TTE capability phrases")
print("Input:", test_text)
print("Matched groups:", groups)
print("Matched terms:", terms)

if groups:
    print("RESULT: PASS - direct evidence detection works on test text.")
else:
    print("RESULT: FAIL - expected TTE capability phrases were not detected.")

# Test 2: Check real opportunity titles from the existing report
path = "data/reports/semantic_match_v2.csv"
df = pd.read_csv(path)

print("\n" + "=" * 70)
print("TEST 2: Existing opportunity titles")
print("=" * 70)

for _, row in df.head(10).iterrows():
    title = str(row.get("title", "") or "")
    matched_groups, matched_terms = get_direct_technical_evidence(
        title, profile
    )

    print(f"\nOpportunity ID: {row.get('opportunity_id')}")
    print(f"Title: {title}")
    print(f"Matched groups: {matched_groups}")
    print(f"Matched terms: {matched_terms}")

print("\n" + "=" * 70)
print("Diagnostic complete. No database changes made.")
print("=" * 70)
