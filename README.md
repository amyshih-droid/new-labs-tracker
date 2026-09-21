# New Labs Tracker

A pipeline to detect **new research labs in the US**, starting with life science. Postdocs, fellows, and computational labs are in scope, because they are early signals of labs that are about to start.

## Goal

Build a database and simple web interface where each row is a **candidate new lab**, with:

- a named PI or company
- institution, department, and research area
- evidence (quote and source link)
- a confidence score and a status (`candidate`, `likely`, `confirmed`, `rejected`)

The main idea is that a lab is an entity and every source produces *signals* about it. Weak evidence from several sources (a grant, a news item, a job ad) can add up to a confident lead.

### Planned sources

| # | Source | Status |
|---|---|---|
| 1.1 | NIH K99/R00 grants (RePORTER API) | Done |
| 1.2 | University, department, and institute news (RSS) | **Done for a first batch of feeds** |
| 1.3 | Department faculty pages (weekly diff) | Not started |
| 1.4 | Incubators and startup facilitators | Partly (BioLabs blog, trade press, funders) |
| 2 | LLM analysis of events, including job postings that mention a lab that does not exist yet (max 3 job sites) | Not started |

## Current pipeline

```
feeds.csv -> fetch.py -> labs.db -> export_leads.py -> potential_leads.csv
```

| Step | File | What it does |
|---|---|---|
| 1 | `feeds.csv` | Registry of RSS feeds: `institution, feed_name, feed_url, category` |
| 2 | `fetch.py` | Downloads each feed, dedupes by article URL, and stores articles in SQLite. Flags `keyword_hit=1` when the title or summary matches a pattern for new faculty, new labs, postdocs, startups, or awards. Faculty-style feeds and trade/incubator/funder feeds use different patterns. |
| 3 | `labs.db` | SQLite database with an `articles` table |
| 4 | `check.py` | Prints articles and keyword hits per feed, to judge which sources are worth keeping |
| 5 | `export_leads.py` | Writes the keyword hits to `potential_leads.csv` |

Written but **not yet run**: `enrich.py` (downloads full article text for hits) and `review_app.py` (a Streamlit app for labeling hits as `new_lab`, `prospective`, `facility`, or `not_relevant`).

## Feeds in `feeds.csv`

| Category | Feeds |
|---|---|
| `university` | MIT (Faculty, Biology, School of Science, All news), JHU (Tech Ventures, Postdocs) |
| `institute` | Whitehead, Broad Institute |
| `med_school` | Harvard Medical School |
| `funder` | Damon Runyon |
| `incubator` | BioLabs blog |
| `trade_news` | Fierce Biotech, BioSpace |

The first run stored about 257 articles, of which 14 were keyword hits.

## What `potential_leads.csv` is

A **screening list**, not a list of confirmed new labs. A keyword hit means an article *might* announce a new lab. A person still has to read it and decide.

| Column | Meaning |
|---|---|
| `institution`, `feed_name`, `category` | Where the article came from |
| `title`, `published`, `url` | The article, its date, and a link |
| `matched_phrase` | The words that triggered the flag |
| `review` | Verdict, to be filled in: `new_lab`, `prospective`, `facility`, or `not_relevant` |
| `notes` | Free text (PI name, reasoning) |

### Review labels

- `new_lab`: names a person or company starting a lab
- `prospective`: an awardee, postdoc, or fellow who may start a lab
- `facility`: new lab space with no named PI
- `not_relevant`: anything else

### Preliminary read of the first 14 hits (from titles only, not yet reviewed)

- **Probably prospective (2):** the two Damon Runyon announcements. They likely name early-career scientists, so they look like the most useful rows.
- **Probably facility (1):** BioLabs Philadelphia expansion.
- **Possible new faculty (1):** MIT HASS "welcomes six new faculty for 2026" (humanities and social sciences, so likely outside a life-science focus).
- **Postdoc programs (4):** JHU Provost's Fellows, a Beckman fellow, and MIT's Quantum postdoc program. Prospective at best.
- **Noise (6):** for example the AAAS election, a postdoc retreat, and research stories.

## Known limitations

- **Keyword hits are noisy.** Phrases like "postdoctoral fellow" and "new member" match unrelated stories.
- **Some hits are old.** 8 of the 14 are dated 2016 to 2025, because some feeds return older items. "New" needs a date check.
- **Feeds only return their latest 10 to 50 items.** Busy feeds should be fetched daily so items are not missed.
- **General news feeds have low yield for wet labs.** Department-level feeds, funder announcements, and structured sources (RePORTER) should be more productive.
- Titles alone are not enough to decide. Full text is needed, which is what `enrich.py` is for.

## Setup

```bash
git clone https://github.com/YOUR-USERNAME/new-labs-tracker.git
cd new-labs-tracker
python3 -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt      # feedparser, trafilatura, pandas, streamlit
```

## Usage

```bash
python fetch.py            # pull feeds and flag keyword hits
python check.py            # per-feed counts and the list of hits
python export_leads.py     # write potential_leads.csv
```

Once `enrich.py` and `review_app.py` are added:

```bash
python enrich.py                 # download full text for hits
streamlit run review_app.py      # label the hits
python export_leads.py           # export with excerpts and verdicts
```

To add a source, add a row to `feeds.csv` and pick a category.

## Next steps

1. **Add a date filter** to `export_leads.py` so only recent items (for example the last 12 months) are exported.
2. **Run `enrich.py` and `review_app.py`** and label 30 to 50 hits. These labels become the test set for the LLM step.
3. **Build `classify.py`.** An LLM reads each hit's full text and returns named candidates, with role (`new_pi`, `postdoc_or_fellow`, `startup_or_company`), wet/dry/mixed/unclear, confidence, and an evidence quote. Compare it against the manual labels.
4. **Build the NIH RePORTER collector (K99/R00).** Structured, mostly biomedical, and it names PIs, so it should give the highest-quality leads.
5. **Add a `labs` table** that merges signals from different sources into one entity per lab (fuzzy match on PI name plus institution).
6. **Add faculty-page monitoring** for about 20 life-science departments (weekly snapshots, with an LLM extracting names).
7. **Add job postings** (up to 3 sites), with the LLM flagging labs that do not exist yet.
8. **Automate weekly** with GitHub Actions and build a simple dashboard (Streamlit): a "new this week" view, filters, and confirm/reject buttons.

## Notes

- Keep API keys in a `.env` file and never commit it. `.env`, `.venv/`, and `__pycache__/` belong in `.gitignore`.
- Check each site's terms of service and `robots.txt` before scraping, especially for job sites.
- Store only public, professional information.