import sqlite3

import pandas as pd

con = sqlite3.connect("labs.db")
for column in ("full_text TEXT", "review TEXT", "notes TEXT"):
    try:
        con.execute(f"ALTER TABLE articles ADD COLUMN {column}")
    except sqlite3.OperationalError:
        pass
con.commit()

df = pd.read_sql(
    "SELECT institution, feed_name, category, title, published, url, "
    "full_text, review, notes FROM articles WHERE keyword_hit=1 "
    "ORDER BY fetched_at DESC", con)
df.to_csv("potential_leads.csv", index=False)
con.close()
reviewed = df["review"].fillna("").ne("").sum()
print(f"Wrote {len(df)} rows ({reviewed} reviewed) to potential_leads.csv")