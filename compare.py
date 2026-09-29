import sqlite3

import pandas as pd

pd.set_option("display.max_colwidth", 60)
pd.set_option("display.width", 220)

con = sqlite3.connect("labs.db")

# Every article that's been classified, regardless of the old keyword_hit flag —
# classify.py now runs on the full set, not just the regex-flagged subset.
df = pd.read_sql("""
    SELECT a.title, a.review AS human_label,
           c.role AS llm_role, c.confidence, c.evidence_quote
    FROM articles a
    JOIN candidates c ON a.url = c.article_url
    ORDER BY a.title
""", con)

df["human_label"] = df["human_label"].replace("", pd.NA)
labeled = df[df["human_label"].notna()].copy()
labeled["agrees"] = labeled["human_label"] == labeled["llm_role"]

print(f"Total classified articles: {len(df)}")
print(f"Of which hand-labeled: {len(labeled)}")

print()
print("=" * 100)
print("ARTICLE-LEVEL COMPARISON (labeled articles only)")
print("=" * 100)
print(labeled[["title", "human_label", "llm_role", "confidence", "agrees"]].to_string(index=False))

print()
print(f"Agreement: {labeled['agrees'].sum()}/{len(labeled)}")
print()
print("Disagreements to look at:")
print(labeled[~labeled["agrees"]][["title", "human_label", "llm_role", "evidence_quote"]].to_string(index=False))

# What the model called on the UNLABELED articles — this is your real "does it
# generalize" check, not just the small labeled set above.
unlabeled = df[df["human_label"].isna()]
print()
print("=" * 100)
print(f"UNLABELED ARTICLES: {len(unlabeled)} classified with no human label yet")
print("=" * 100)
print(unlabeled["llm_role"].value_counts().to_string())

con.close()