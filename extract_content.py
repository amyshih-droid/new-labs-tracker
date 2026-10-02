"""Extract structured content (names, departments, research domains/techniques) from
articles already classified as 'prospective' or 'facility' in the candidates table.

This runs AFTER classify.py, not instead of it — classify.py decides relevance,
this script pulls out the details from the articles that passed that screen.

Usage:
    python extract_content.py          # only rows not yet extracted
    python extract_content.py --all    # reprocess everything (after a prompt change)
"""
import argparse
import json
import sqlite3
import time
from datetime import datetime, timezone

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

MODEL = "gpt-6-luna"
REASONING_EFFORT = "medium"
client = OpenAI()

PROMPT = """Read this news article and extract structured details about the person(s),
company, or facility it describes.

Article title: {title}
Institution (from the source feed): {institution}
Text:
{text}

Return a JSON object of exactly this form:
{{
  "names": ["..."],
  "departments": ["..."],
  "domains": ["..."]
}}

Rules:
- "names": the specific person(s) who are the subject of the article (the new PI,
  postdoc, fellow, or company founder) — full name if given, partial name (e.g. just
  a last name) if that's all the text provides. Do NOT include people only mentioned
  in passing (e.g. a department chair quoted congratulating someone else, a
  co-author listed only in a citation). Empty list if the article is about a
  facility/company with no named individual.
- "departments": department, institute, lab, or center names directly associated
  with the person(s) or facility above — not every organization mentioned in the
  article.
- "domains": specific research domains, diseases, organisms, or experimental
  techniques/methods explicitly named in the text — e.g. "immunology",
  "breast cancer", "NGS", "bacterial culture", "flow cytometry", "ELISA",
  "CRISPR", "mass spectrometry". Use short noun phrases copied from or directly
  based on the text, not full sentences. Do not invent a domain/technique that
  isn't actually mentioned — if the article doesn't specify one, return an empty
  list rather than guessing from the institution or department name alone.

Every name and domain you list must actually be supported by the text above —
do not infer or guess beyond what's written."""


def grounded(value, text):
    """Cheap hallucination check: is this extracted value actually present in the
    source text (case-insensitive, allowing for minor punctuation differences)?"""
    if not value or not text:
        return False
    return value.lower() in text.lower()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true",
                     help="reprocess every prospective/facility article, including "
                          "ones already extracted (use after a prompt change). "
                          "Default: only articles not yet extracted.")
    args = ap.parse_args()

    con = sqlite3.connect("labs.db")
    for col in ("names TEXT", "departments TEXT", "domains TEXT",
                "names_grounded TEXT", "extracted_at TEXT"):
        try:
            con.execute(f"ALTER TABLE candidates ADD COLUMN {col}")
        except sqlite3.OperationalError:
            pass
    con.commit()

    sql = ("SELECT c.id, a.url, a.institution, a.title, a.full_text "
           "FROM candidates c JOIN articles a ON c.article_url = a.url "
           "WHERE c.role IN ('prospective', 'facility') "
           "AND a.full_text IS NOT NULL AND a.full_text<>''")
    if not args.all:
        sql += " AND (c.extracted_at IS NULL OR c.extracted_at = '')"
    rows = con.execute(sql).fetchall()
    mode = "all prospective/facility articles" if args.all else "new, unextracted articles"
    print(f"{len(rows)} {mode} to extract")

    for cid, url, inst, title, text in rows:
        try:
            resp = client.chat.completions.create(
                model=MODEL,
                reasoning_effort=REASONING_EFFORT,
                response_format={"type": "json_object"},
                messages=[{"role": "user", "content": PROMPT.format(
                    title=title, institution=inst, text=text[:12000])}],
            )
            data = json.loads(resp.choices[0].message.content)
            names = data.get("names") or []
            departments = data.get("departments") or []
            domains = data.get("domains") or []
        except Exception as e:
            print(f"ERROR  {title[:55]}: {e}")
            continue

        name_grounding = {n: grounded(n, text) for n in names}
        ungrounded = [n for n, ok in name_grounding.items() if not ok]
        if ungrounded:
            print(f"  WARNING ungrounded name(s) {ungrounded!r} in: {title[:55]}")

        con.execute(
            "UPDATE candidates SET names=?, departments=?, domains=?, "
            "names_grounded=?, extracted_at=? WHERE id=?",
            (json.dumps(names), json.dumps(departments), json.dumps(domains),
             json.dumps(name_grounding), datetime.now(timezone.utc).isoformat(), cid))
        con.commit()
        print(f"{title[:55]:55}  names={names}  depts={departments}  domains={domains}")
        time.sleep(0.3)

    con.close()


if __name__ == "__main__":
    main()