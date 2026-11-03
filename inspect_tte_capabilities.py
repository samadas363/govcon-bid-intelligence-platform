from pprint import pprint
from src.company_profile import get_company_profile

profile = get_company_profile()

print("=" * 70)
print("TTE PROFILE FIELDS AVAILABLE FOR MATCHING")
print("=" * 70)

fields_to_inspect = [
    "company_name",
    "target_naics_codes",
    "core_competencies",
    "keyword_groups",
    "project_experience",
    "differentiators",
]

for field in fields_to_inspect:
    print(f"\n{field.upper()}:")
    if field in profile:
        pprint(profile[field])
    else:
        print("Field not present in profile.")

