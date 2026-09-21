import csv
import re
import sqlite3
from datetime import datetime, timezone

import feedparser

DB = "labs.db"
FEEDS_FILE = "feeds.csv"

feedparser.USER_AGENT = "Mozilla/5.0 (compatible; new-labs-tracker/0.1)"

# University, institute, and med-school news: new faculty / new PIs / new labs
FACULTY_KEYWORDS = re.compile(
    r"join(s|ed|ing)? (the )?(faculty|department|institute)|new faculty|"
    r"welcomes? .{0,40}faculty|incoming (assistant|faculty|professor)|"
    r"new (assistant )?professor|new (member|fellow|group leader|principal investigator)|"
    r"new lab|establish\w* (a )?(new )?(research )?(lab|center|institute)|"
    r"launch\w* (a |his |her |their )?(new )?lab|"
    r"start\w* (a |his |her |their )?(own )?lab|postdoctoral fellow",
    re.I,
)

# Trade press, incubators, funders: new startups, new facilities, new awardees
OTHER_KEYWORDS = re.compile(
    r"emerg\w+ from stealth|launch\w* (with \$|a new (lab|company|startup))|"
    r"seed (round|funding)|series [ab] (financing|round|funding)|"
    r"founded by|spin\w* out|new (research )?(lab|facility|headquarters)|"
    r"opens? (a |its )?(new )?(lab|facility)|postdoc\w*|"
    r"new (fellows|awardees|scholars|investigators)|"
    r"announces? .{0,40}(fellows|awardees|scholars|investigators)",
    re.I,
)
OTHER_CATEGORIES = {"trade_news", "incubator", "funder"}


def init_db():
    con = sqlite3.connect(DB)
    con.execute("""
        CREATE TABLE IF NOT EXISTS articles (
            url TEXT PRIMARY KEY,
            institution TEXT,
            feed_name TEXT,
            category TEXT,
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
        reader = csv.DictReader(f, skipinitialspace=True)
        for row in reader:
            row = {k: (v or "").strip() for k, v in row.items()}
            label = f'{row["institution"]} / {row["feed_name"]}'
            pattern = OTHER_KEYWORDS if row["category"] in OTHER_CATEGORIES else FACULTY_KEYWORDS

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
                    "(url, institution, feed_name, category, title, summary, published, "
                    "fetched_at, keyword_hit) VALUES (?,?,?,?,?,?,?,?,?)",
                    (
                        link, row["institution"], row["feed_name"], row["category"],
                        e.get("title"), e.get("summary"), e.get("published"),
                        datetime.now(timezone.utc).isoformat(),
                        int(bool(pattern.search(text))),
                    ),
                )
                new += cur.rowcount
            print(f"{label}: {new} new (of {len(feed.entries)} in feed)")

    con.commit()
    con.close()


if __name__ == "__main__":
    main()