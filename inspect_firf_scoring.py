from pprint import pprint
from src.company_profile import get_company_profile
from src.qualification_engine import qualify_all_opportunities

profile = get_company_profile()
results = qualify_all_opportunities()

print("=" * 75)
print("FIRF QUALIFICATION RESULT")
print("=" * 75)

matches = [
    result for result in results
    if "FIRF" in str(result.get("title", "")).upper()
]

if not matches:
    print("No result with FIRF in its title was found.")
    print("Available result keys:")
    if results:
        pprint(list(results[0].keys()))
else:
    for result in matches:
        pprint(result)

print("\n" + "=" * 75)
print("TTE KEYWORD GROUPS")
print("=" * 75)
pprint(profile["keyword_groups"])
