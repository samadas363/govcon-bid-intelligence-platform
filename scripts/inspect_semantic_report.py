import pandas as pd

df = pd.read_csv("data/reports/semantic_match_v2.csv")

print("Columns:")
for column in df.columns:
    print("-", column)

print("\nFirst record:")
print(df.head(1).to_string(index=False))
