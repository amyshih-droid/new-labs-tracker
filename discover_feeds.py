import csv
import re
import time
from urllib.parse import urljoin

import feedparser
import requests

UA = "Mozilla/5.0 (compatible; new-labs-tracker/0.1)"
COMMON = ["/feed", "/feed/", "/rss", "/rss.xml", "/news/feed", "/news/rss",
          "/news/all/rss", "/rss/feed", "/index.xml", "/atom.xml"]
LINK_TAG = re.compile(r'<link[^>]+type=["\']application/(?:rss|atom)\+xml["\'][^>]*>', re.I)
HREF = re.compile(r'href=["\']([^"\']+)["\']', re.I)


def test(url):
    try:
        f = feedparser.parse(url, agent=UA)
        if f.get("status") == 200 and f.entries:
            return len(f.entries), f.entries[0].get("title", "")
    except Exception:
        pass
    return None


def discover(page_url):
    urls = []
    try:
        html = requests.get(page_url, headers={"User-Agent": UA}, timeout=15).text
        for tag in LINK_TAG.findall(html):
            m = HREF.search(tag)
            if m:
                urls.append(urljoin(page_url, m.group(1)))
    except Exception as e:
        print(f"  page fetch failed: {e}")
    root = "/".join(page_url.split("/")[:3])          # scheme + domain
    urls += [root + p for p in COMMON]
    urls += [page_url.rstrip("/") + p for p in COMMON[:4]]
    seen, working = set(), []
    for u in urls:
        if u in seen:
            continue
        seen.add(u)
        result = test(u)
        if result:
            working.append((u, *result))
        time.sleep(0.5)
    return working


with open("candidates.csv", newline="") as f, open("discovered.csv", "w", newline="") as out:
    w = csv.writer(out)
    w.writerow(["institution", "feed_name", "feed_url", "entries", "latest_title"])
    for row in csv.DictReader(f):
        print(row["institution"])
        found = discover(row["page_url"])
        if not found:
            print("  no working feed found")
        for url, n, title in found:
            print(f"  OK {n:>3} entries  {url}")
            w.writerow([row["institution"], "News", url, n, title])