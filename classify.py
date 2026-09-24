import json
import sqlite3
import time
from datetime import datetime, timezone

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

MODEL = "gpt-5.4-nano"
client = OpenAI()

PROMPT = """You are screening a news article to see if it signals a NEW research lab
in the US, in academia or industry. This includes wet, dry, and computational labs.

Use these categories, based on what the text actually says — not what seems likely:

- "new_pi_hired": a person is named as joining/starting as an assistant professor,
  group leader, or independent PI, but the text does NOT say their lab is operating
  yet (no start date passed, no lab name, no "his lab studies X" in present tense).
- "postdoc_or_fellow": a person is a postdoc, fellow, or award recipient who is not
  yet an independent PI. Aspirational language ("hopes to run her own lab someday")
  still belongs here, not in new_lab.
- "startup_or_company": a company or spinout is named as newly founded/launched.
- "facility_only": new lab space, building, or department restructuring, with no
  specific person's own lab named as newly operating.
- "not_relevant": none of the above (research findings, elections, obituaries,
  general events).

Only mark "is_new_lab": true if the text gives evidence the lab is ALREADY OPERATING
or explicitly starting very soon (e.g. "his lab, launched this fall, studies...",
"opening her lab in January", present-tense description of the lab's ongoing work).
Being hired, appointed, or promoted is NOT enough on its own — mark those
"new_pi_hired" with is_new_lab: false, even if the person is clearly a new PI.

Article title: {title}
Source: {institution} / {feed_name} ({category})
Text:
{text}

Return a JSON object of the form {{"candidates": [...]}}. The list has one object per
distinct person/company that could be a lab lead. Use an empty list if none apply.
Each object:
{{
  "pi_name": "... or null",
  "institution": "...",
  "department": "... or null",
  "research_area": "... or null",
  "role": "new_pi_hired" | "postdoc_or_fellow" | "startup_or_company" | "facility_only" | "not_relevant",
  "is_new_lab": true/false,
  "lab_type": "wet" | "dry" | "mixed" | "unclear",
  "confidence": 0.0-1.0,
  "evidence_quote": "short quote, under 15 words, that most directly supports the role/is_new_lab call",
  "reasoning": "one sentence"
}}
Be conservative. If the text only says someone was hired/appointed/awarded, that is
new_pi_hired or postdoc_or_fellow with is_new_lab false — not new_lab."""


def main():
    con = sqlite3.connect("labs.db")
    con.execute("""CREATE TABLE IF NOT EXISTS candidates (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        article_url TEXT,
        pi_name TEXT,
        institution TEXT,
        department TEXT,
        research_area TEXT,
        role TEXT,
        is_new_lab INTEGER,
        lab_type TEXT,
        confidence REAL,
        evidence_quote TEXT,
        reasoning TEXT,
        created_at TEXT)""")

    rows = con.execute(
        "SELECT url, institution, feed_name, category, title, full_text, review "
        "FROM articles WHERE keyword_hit=1 AND full_text IS NOT NULL AND full_text<>''"
    ).fetchall()
    print(f"{len(rows)} articles to classify")

    for url, inst, feed, cat, title, text, human_review in rows:
        con.execute("DELETE FROM candidates WHERE article_url=?", (url,))  # allow re-runs
        try:
            resp = client.chat.completions.create(
                model=MODEL,
                response_format={"type": "json_object"},
                messages=[{"role": "user", "content": PROMPT.format(
                    title=title, institution=inst, feed_name=feed, category=cat,
                    text=text[:12000])}],
            )
            items = json.loads(resp.choices[0].message.content).get("candidates", [])
        except Exception as e:
            print(f"ERROR  {title[:55]}: {e}")
            continue

        roles = []
        for it in items:
            con.execute(
                "INSERT INTO candidates (article_url, pi_name, institution, department, "
                "research_area, role, is_new_lab, lab_type, confidence, evidence_quote, "
                "reasoning, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (url, it.get("pi_name"), it.get("institution"), it.get("department"),
                 it.get("research_area"), it.get("role"), int(bool(it.get("is_new_lab"))),
                 it.get("lab_type"), it.get("confidence"), it.get("evidence_quote"),
                 it.get("reasoning"), datetime.now(timezone.utc).isoformat()))
            roles.append(it.get("role"))
        flag = "  <-- human said: " + human_review if human_review else ""
        print(f"{title[:55]:55}  ->  {roles}{flag}")
        con.commit()
        time.sleep(0.3)

    con.close()


if __name__ == "__main__":
    main()