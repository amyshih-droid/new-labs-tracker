"""One-time sync: pushes the corrected human_label values from
model_comparison_annotation.csv back into articles.review in labs.db, matched by url.

Run this once after editing the CSV, before re-running compare.py / compare_models.py.
"""
import sqlite3

import pandas as pd

CSV_PATH = "model_comparison_annotation.csv"

df = pd.read_csv(CSV_PATH)
df = df[["url", "human_label"]].dropna(subset=["url"])

con = sqlite3.connect("labs.db")

changed = 0
missing = 0
for url, new_label in df.itertuples(index=False):
    cur = con.execute("SELECT review FROM articles WHERE url=?", (url,)).fetchone()
    if cur is None:
        missing += 1
        continue
    old_label = cur[0]
    new_label = new_label if pd.notna(new_label) and new_label != "" else None
    if old_label != new_label:
        con.execute("UPDATE articles SET review=? WHERE url=?", (new_label, url))
        changed += 1
        print(f"  {url[:70]:70}  {old_label!r} -> {new_label!r}")

con.commit()
con.close()
print(f"\n{changed} rows updated, {missing} urls from the CSV not found in labs.db")