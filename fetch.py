import csv
import re
import sqlite3
from datetime import datetime, timezone

import feedparser

DB = "labs.db"
FEEDS_FILE = "feeds.csv"

feedparser.USER_AGENT = "Mozilla/5.0 (compatible; new-labs-tracker/0.1)"

KEYWORDS = re.compile(
    r"join(s|ed|ing)? (the )?(faculty|department)|new faculty|welcome[sd]?|incoming|"
    r"assistant professor|new lab|establish\w* (a )?(new )?lab|launch\w* (a )?lab|"
    r"start\w* (a |his |her |their )?lab|spin ?out|startup|founded",
    re.I,
)


def init_db():
    con = sqlite3.connect(DB)
    con.execute("""
        CREATE TABLE IF NOT EXISTS articles (
            url TEXT PRIMARY KEY,
            institution TEXT,
            feed_name TEXT,
            title TEXT,
            summary TEXT,
            published TEXT,
            fetched_at TEXT,
            keyword_hit INTEGER,
            llm_status TEXT DEFAULT 'pending'
        )
    """)
    return con


def main():
    con = init_db()
    with open(FEEDS_FILE, newline="") as f:
        for row in csv.DictReader(f):
            label = f'{row["institution"]} / {row["feed_name"]}'
            feed = feedparser.parse(row["feed_url"])
            status = feed.get("status", "no response")

            if status != 200 or not feed.entries:
                print(f"WARNING {label}: status={status}, entries={len(feed.entries)}")
                continue

            new = 0
            for e in feed.entries:
                link = e.get("link")
                if not link:
                    continue
                text = f"{e.get('title', '')} {e.get('summary', '')}"
                cur = con.execute(
                    "INSERT OR IGNORE INTO articles "
                    "(url, institution, feed_name, title, summary, published, fetched_at, keyword_hit) "
                    "VALUES (?,?,?,?,?,?,?,?)",
                    (
                        link,
                        row["institution"],
                        row["feed_name"],
                        e.get("title"),
                        e.get("summary"),
                        e.get("published"),
                        datetime.now(timezone.utc).isoformat(),
                        int(bool(KEYWORDS.search(text))),
                    ),
                )
                new += cur.rowcount
            print(f"{label}: {new} new (of {len(feed.entries)} in feed)")

    con.commit()
    con.close()


if __name__ == "__main__":
    main()