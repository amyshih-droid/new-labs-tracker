import sqlite3
import time

import trafilatura

DB = "labs.db"

con = sqlite3.connect(DB)

# Add the columns if this is the first time enrich.py has run.
# (fetch.py's CREATE TABLE only includes them on a fresh database.)
for col in ("full_text TEXT", "review TEXT", "notes TEXT"):
    try:
        con.execute(f"ALTER TABLE articles ADD COLUMN {col}")
    except sqlite3.OperationalError:
        pass  # column already exists, safe to ignore
con.commit()

rows = con.execute(
    "SELECT url, title FROM articles "
    "WHERE (full_text IS NULL OR full_text='')"
).fetchall()
print(f"{len(rows)} articles to fetch")

for url, title in rows:
    html = trafilatura.fetch_url(url)
    text = trafilatura.extract(html) if html else None
    con.execute("UPDATE articles SET full_text=? WHERE url=?", (text or "", url))
    con.commit()
    status = "OK  " if text else "FAIL"
    print(f"{status} {title[:70]}  ({url})")
    time.sleep(1)  # be polite to the sites, avoid hammering their servers

con.close()
print("Done.")