import sqlite3
import pandas as pd

con = sqlite3.connect("labs.db")
total = pd.read_sql("SELECT COUNT(*) AS n FROM articles", con).n[0]
hits = pd.read_sql("SELECT COUNT(*) AS n FROM articles WHERE keyword_hit=1", con).n[0]
print(f"Total articles: {total}, keyword hits: {hits}\n")

df = pd.read_sql(
    "SELECT institution, feed_name, title FROM articles WHERE keyword_hit=1 LIMIT 25", con
)
pd.set_option("display.max_colwidth", 90)
print(df.to_string(index=False))