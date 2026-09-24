import sqlite3

import pandas as pd

con = sqlite3.connect("labs.db")
df = pd.read_sql(
    "SELECT institution, feed_name, category, title, published, url, "
    "full_text, review, notes FROM articles WHERE keyword_hit=1 "
    "ORDER BY fetched_at DESC", con)
df.to_csv("potential_leads.csv", index=False)
print(f"Wrote {len(df)} rows to potential_leads.csv")