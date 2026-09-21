import sqlite3
import pandas as pd
from fetch import FACULTY_KEYWORDS, OTHER_KEYWORDS, OTHER_CATEGORIES

con = sqlite3.connect("labs.db")
df = pd.read_sql(
    "SELECT institution, feed_name, category, title, published, url, summary "
    "FROM articles WHERE keyword_hit=1 ORDER BY fetched_at DESC", con)


def matched(row):
    pattern = OTHER_KEYWORDS if row["category"] in OTHER_CATEGORIES else FACULTY_KEYWORDS
    m = pattern.search(f'{row["title"]} {row["summary"] or ""}')
    return m.group(0) if m else ""


df["matched_phrase"] = df.apply(matched, axis=1)
df["review"] = ""   # fill in: new_lab / prospective / facility / not_relevant
df["notes"] = ""
df = df.drop(columns="summary")
df.to_csv("potential_leads.csv", index=False)
print(f"Wrote {len(df)} rows to potential_leads.csv")