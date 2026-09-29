# New Labs Tracker

A pipeline to detect **new research labs in the US**, academic or industry, wet/dry/computational
all in scope. Postdocs, fellows, and early-career award recipients count as **prospective**
signals, because they're often the earliest sign a new lab is coming.

## Goal

Build a database (and eventually a simple web interface) where each row is a **candidate new
lab**, with:

- a named PI or company
- institution, department, and research area
- evidence (quote and source link)
- a confidence score and status (`candidate`, `likely`, `confirmed`, `rejected`)

The core idea: a lab is an entity, and every source produces *signals* about it. Weak evidence
from several independent sources (a grant, a news item, a job ad) should combine into a
confident lead — no single source is trusted alone. **This multi-source merge is not built yet**;
right now the pipeline covers one source (RSS news) end to end, from ingestion through
LLM classification and human evaluation.

### Planned sources

| # | Source | Status |
|---|---|---|
| 1.1 | NIH K99/R00 grants (RePORTER API) | done |
| 1.2 | University/institute/med-school news (RSS) | **Done** — full pipeline built, tuned, evaluated |
| 1.3 | Department faculty pages (weekly diff for new names) | Not started |
| 1.4 | Incubators and startup facilitators | Partly — BioLabs blog, trade press, funder feeds |
| 2 | LLM detection of implied new labs (e.g. job ads referencing a not-yet-existing lab) | Not started |
| — | Job postings (max 3 sites: HigherEdJobs, Science Careers, Nature Careers) | Not started |

## Pipeline

```
feeds.csv → fetch.py → labs.db (articles)
                              ↓
                         enrich.py  (full-text retrieval)
                              ↓
              ┌───────────────┴───────────────┐
              ↓                                ↓
   review_app.py (human label)      classify.py (LLM label)
              ↓                                ↓
              └───────────────┬───────────────┘
                              ↓
                         compare.py  (agreement check)
```

| File | What it does |
|---|---|
| `feeds.csv` | Registry of RSS feeds: `institution, feed_name, feed_url, category`. Categories: `university`, `institute`, `med_school`, `funder`, `incubator`, `trade_news`. |
| `fetch.py` | Downloads each feed via `feedparser`, dedupes by article URL (`INSERT OR IGNORE`), and stores articles in `labs.db`'s `articles` table. Flags `keyword_hit=1` using one of two regex patterns depending on feed category (faculty/hire language vs. startup/award language). Skips dead feeds with a warning instead of failing the whole run. |
| `discover_feeds.py` | Given a list of institution homepages, scrapes for RSS `<link>` tags and tries common feed paths, to help grow `feeds.csv`. |
| `enrich.py` | For flagged articles, downloads the live page and extracts clean article body text via `trafilatura`, writing it into `articles.full_text`. Idempotent — only processes rows missing full text. |
| `check.py` | Prints per-feed article/hit counts, for a quick sanity check on source quality. |
| `export_leads.py` | Writes keyword hits (with human review/notes) to `potential_leads.csv`. |
| `review_app.py` | Streamlit app (`streamlit run review_app.py`) for human labeling. Shows one flagged article at a time with the triggering keyword highlighted; saves a verdict straight to `articles.review`. |
| `sync_labels.py` | One-time/as-needed sync: pushes corrected labels from a CSV (e.g. after editing `model_comparison_annotation.csv`) back into `articles.review`, matched by URL. |
| `classify.py` | Sends each article's full text to an LLM, which returns exactly one classification for the whole article: `prospective`, `facility`, or `not_relevant` (see below), plus a confidence score and a short verbatim evidence quote. Writes to the `candidates` table. Safe to re-run — deletes and re-inserts per article. |
| `compare.py` | Joins `articles.review` (human label) against `candidates.role` (LLM label) and reports agreement, printing the disagreements for manual triage. |

### Human/LLM label scheme

Both humans and the LLM classify each article into exactly one of three categories:

- **`prospective`** — a named person who may eventually start their own lab (a newly hired
  PI, an early-career postdoc/fellow on an independent-research-track award, or a newly
  founded startup/spinout). Explicitly *excludes* general honorific awards to established
  researchers, retrospective profiles with no fresh hire news, program launches with no named
  individual yet, and ordinary company hiring — *unless* the award grants real operating
  resources (lab space, independent funding), which still counts.
- **`facility`** — new lab space, a new building, or a department being newly formed/
  restructured, located in the US, with no individual's own lab as the subject. Explicitly
  *excludes* leadership transitions at existing (not newly formed) units, non-US facilities,
  incidental facility mentions, and new equipment/instruments built by an existing team.
- **`not_relevant`** — everything else.

The full category definitions, with the negative examples above, live in `classify.py`'s
`PROMPT`.

## Model evaluation

Before settling on a model, `classify_experiment.py` and `compare_models.py` were used to
run the same prompt across four configs — `gpt-5.4-nano`, and `gpt-6-luna` at `high`/`medium`/
`low` reasoning effort — against a fully hand-labeled set of 228 articles, with results in
`results/*.csv` and a side-by-side comparison in `model_comparison.csv` /
`model_disagreements.csv`.

Findings:
- **`gpt-5.4-nano`** never missed a true `prospective`/`facility` article (100% recall on both),
  but at heavy precision cost (~44 false positives out of 228).
- **`gpt-6-luna` (medium)** had the best balance of accuracy and precision, and was — in a few
  cases — more *correct* than the initial ground truth (e.g. correctly excluding non-US BioLabs
  facility posts that had been mislabeled `facility`).

**Current choice: `gpt-6-luna` at `medium` reasoning effort.** After several rounds of
prompt refinement and ground-truth correction (see `compare_output.txt` for the latest run),
agreement with human labels is **~97% (221–222/228)**. Remaining disagreements are
almost entirely genuine scope-boundary judgment calls rather than model or prompt errors — e.g.
whether a postbac research internship (vs. a postdoc) counts as `prospective`, whether an
unfilled job posting counts without a named hire, and whether an obituary describing a
just-formed lab should count given the lab's now-uncertain future. A small remainder reflects
ordinary LLM run-to-run variance on borderline articles, not a fixable defect.

`sync_labels.py` exists because ground-truth corrections were made in a CSV
(`model_comparison_annotation.csv`) during this process and needed to be pushed back into
`labs.db` — keep the CSV and the database in sync if you relabel again.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Create a `.env` file (not committed — see `.gitignore`) with:
```
OPENAI_API_KEY=sk-...
```

## Usage

```bash
python fetch.py                          # pull RSS feeds into labs.db
python enrich.py                         # fetch full text for keyword hits
streamlit run review_app.py              # human-label flagged articles (optional)
python classify.py                       # LLM-classify articles into labs.db
python compare.py > compare_output.txt   # check LLM vs. human agreement
```

To re-run a model/reasoning-level comparison:
```bash
python classify_experiment.py --labeled-only   # or --from-candidates for the full set
python compare_models.py
```

## Known limitations

- Only one of the five planned sources (RSS news) is fully built.
- No cross-source corroboration yet — a single article's `prospective`/`facility` call is
  currently trusted on its own; the project's original design intends this only as one weak
  signal among several, combined later into a confidence score.
- `feeds.csv` currently mixes US and non-US sources (e.g. the BioLabs blog covers global
  locations); `classify.py`'s prompt filters non-US facilities at classification time, but
  `fetch.py`'s keyword filter does not — worth reviewing if feed volume grows.
- No automated hallucination/grounding guardrails are currently wired into `classify.py` (a
  verbatim-quote check and schema validation were prototyped earlier but are not in the
  current version) — `evidence_quote` should be spot-checked against `full_text` periodically,
  especially for `prospective` verdicts.
- No scheduling yet — everything runs manually.

## Next steps

1. Decide and document the remaining scope judgment calls (postbac vs. postdoc, job postings,
   obituaries with newly-formed labs) so future similar articles are handled consistently.
2. Build the NIH RePORTER K99/R00 collector — likely the highest-precision untapped source.
3. Add department faculty-page monitoring (~20 life-science departments, weekly diff).
4. Add a job-posting collector (max 3 sites) for phantom-lab detection.
5. Merge signals across sources into a single `labs` table with fuzzy PI/institution
   matching and a combined confidence score — this is where a single source's `prospective`
   call stops being trusted alone.
6. Automate weekly runs via GitHub Actions; build a simple dashboard.