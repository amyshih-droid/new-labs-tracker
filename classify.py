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

PROMPT = """You are screening a news article to see if it signals a NEW research lab
in the US, in academia or industry. This includes wet, dry, and computational labs.

Classify using exactly these three categories, based on what the text actually says —
not what seems likely:

- "prospective": a NAMED person who may eventually start their own lab — this
  includes a newly hired assistant professor/group leader/PI (even if the text
  doesn't say their lab is operating yet), or an early-career postdoc/fellow/award
  recipient whose fellowship is specifically aimed at supporting independent
  research careers (e.g. K99/R00-style awards, named foundation fellowships like
  Damon Runyon, Beckman, Provost's Postdoctoral Fellows), including being named as
  part of a cohort/class of such fellows, even without explicit language about a
  future lab. Also includes a newly founded startup/spinout company.
  Do NOT use "prospective" for:
    * a general honorific/recognition award to an already-established, senior
      researcher (e.g. a Guggenheim Fellowship, a lifetime achievement award,
      election to a society) — these recognize existing work, not a launch, and
      grant no operating resources.
      IMPORTANT EXCEPTION: an award or competition that grants an early-career
      researcher independent funding, OR grants a company real lab space/bench
      space to begin operating (e.g. a "Golden Ticket"-style incubator competition
      win, a residency award), IS "prospective" — the test is whether the award
      gives the recipient new operating resources to start research/company
      activity, not merely whether the word "award" or "competition" appears.
    * a retrospective or interview-style profile of a person's ongoing research
      or career (e.g. "3 Questions:", "Meet the...", a Q&A/podcast format) unless
      the article's actual news is that this person just joined or was just hired.
    * a program or fellowship being launched/announced with no specific named
      individual fellow yet (e.g. "X launches a postdoctoral fellowship program") —
      that is "not_relevant" until individual fellows are actually named.
    * a company's ordinary hiring/staffing/growth activity with no newly founded
      entity named (e.g. "raised a Series B and is now hiring") — that alone is
      "not_relevant".

- "facility": new lab space, a new building, or a department being newly FORMED or
  RESTRUCTURED (e.g. one department splitting into two), located in the US, with no
  specific person's own individual lab named as the subject. If a person is named as
  chairing or leading such a newly formed/restructured department, that is
  "facility" — not "prospective" — unless the text separately describes that
  person's own individual research lab as operating.
  Do NOT use "facility" for:
    * a person named as the new director/head/chair of an EXISTING, ALREADY-
      OPERATING unit (department, lab, center, section) that is not being newly
      formed or restructured — a routine leadership transition at a stable unit is
      "not_relevant", even if the unit's name includes the word "laboratory" or
      "center".
    * any lab, facility, or incubator location OUTSIDE THE US — this project only
      tracks US labs. If the institution/city/country named is not in the US,
      classify as "not_relevant" regardless of how the facility itself is described.
    * a facility or renovation mentioned only in passing while the article's actual
      subject is something else (e.g. a campus sustainability/climate article that
      mentions a future lab inside a building being renovated for energy reasons).
    * new equipment, instruments, or technology built by an existing team (e.g. "a
      robotic reconfigurable lab system") — that is a research output, not a new
      physical research facility or department.

- "not_relevant": none of the above (research findings, elections, obituaries,
  general events, retrospective profiles, program launches with no named individual,
  non-US facilities, routine leadership transitions at existing units, or an
  incidental mention that isn't the actual subject of the article — e.g.
  "postdoctoral fellowship" appearing only in a funding acknowledgment).

Article title: {title}
Source: {institution} / {feed_name} ({category})
Text:
{text}

Return exactly one JSON object of the form {{"classification": {{...}}}} for the
article as a whole. Do not return one result per person. Choose the single role that
best describes the article's main subject:
{{
  "role": "prospective" | "facility" | "not_relevant",
  "confidence": 0.0-1.0,
  "evidence_quote": "short quote, under 15 words, copied verbatim from the text above,
    that most directly supports the role call",
  "reasoning": "one sentence"
}}"""


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
        confidence REAL,
        evidence_quote TEXT,
        reasoning TEXT,
        created_at TEXT)""")

    rows = con.execute(
        "SELECT url, institution, feed_name, category, title, full_text, review "
        "FROM articles WHERE full_text IS NOT NULL AND full_text<>''"
    ).fetchall()
    print(f"{len(rows)} articles to classify")

    for url, inst, feed, cat, title, text, human_review in rows:
        con.execute("DELETE FROM candidates WHERE article_url=?", (url,))  # allow re-runs
        try:
            resp = client.chat.completions.create(
                model=MODEL,
                reasoning_effort=REASONING_EFFORT,
                response_format={"type": "json_object"},
                messages=[{"role": "user", "content": PROMPT.format(
                    title=title, institution=inst, feed_name=feed, category=cat,
                    text=text[:12000])}],
            )
        except Exception as e:
            print(f"ERROR  {title[:55]}: {e}")
            continue

        classification = json.loads(resp.choices[0].message.content).get(
            "classification", {})
        role = classification.get("role")
        if role not in {"prospective", "facility", "not_relevant"}:
            raise ValueError(f"invalid article role: {role!r}")
        con.execute(
            "INSERT INTO candidates (article_url, pi_name, institution, department, "
            "research_area, role, confidence, evidence_quote, reasoning, created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (url, None, inst, None, None, role, classification.get("confidence"),
             classification.get("evidence_quote"), classification.get("reasoning"),
             datetime.now(timezone.utc).isoformat()))
        flag = "  <-- human said: " + human_review if human_review else ""
        print(f"{title[:55]:55}  ->  {role}{flag}")
        con.commit()
        time.sleep(0.3)

    con.close()


if __name__ == "__main__":
    main()