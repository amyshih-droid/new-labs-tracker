import sqlite3
import pandas as pd

con = sqlite3.connect("labs.db")
pd.set_option("display.max_colwidth", 90)
pd.set_option("display.width", 200)

summary = pd.read_sql("""
    SELECT institution, feed_name, category,
           COUNT(*) AS articles, SUM(keyword_hit) AS hits
    FROM articles
    GROUP BY institution, feed_name, category
    ORDER BY hits DESC
""", con)
print(summary.to_string(index=False))

print("\nKeyword hits:\n")
hits = pd.read_sql(
    "SELECT institution, feed_name, title FROM articles WHERE keyword_hit=1 "
    "ORDER BY institution, feed_name LIMIT 80", con)
print(hits.to_string(index=False))