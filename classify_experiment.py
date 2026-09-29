"""Run the SAME classification prompt under several model / reasoning-effort configs.

Each config writes its own CSV in results/, so nothing overwrites your `candidates`
table. Re-running skips articles a config has already classified successfully, so an
interrupted run can simply be restarted.

Usage:
    python classify_experiment.py --labeled-only --limit 5     # cheap smoke test
    python classify_experiment.py --labeled-only               # your hand-labeled articles
    python classify_experiment.py                              # every article with full_text
    python classify_experiment.py --configs luna_high luna_low # just some configs
"""
import argparse
import csv
import json
import os
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from dotenv import load_dotenv
from openai import OpenAI

from classify import PROMPT  # single source of truth for the prompt text

load_dotenv()
client = OpenAI()

VALID_ROLES = {"prospective", "facility", "not_relevant"}
OUT_DIR = "results"

# effort=None means "don't send a reasoning setting" (your current nano behavior).
CONFIGS = {
    "nano":        {"model": "gpt-5.4-nano", "effort": None},
    "luna_high":   {"model": "gpt-6-luna",   "effort": "high"},
    "luna_medium": {"model": "gpt-6-luna",   "effort": "medium"},
    "luna_low":    {"model": "gpt-6-luna",   "effort": "low"},
}

FIELDS = ["url", "title", "role", "confidence", "evidence_quote", "reasoning",
          "error", "latency_s", "prompt_tokens", "completion_tokens",
          "reasoning_tokens"]


def classify_one(cfg, row):
    url, inst, feed, cat, title, text = row
    out = {k: "" for k in FIELDS}
    out.update(url=url, title=title)

    kwargs = dict(
        model=cfg["model"],
        response_format={"type": "json_object"},
        messages=[{"role": "user", "content": PROMPT.format(
            title=title, institution=inst, feed_name=feed, category=cat,
            text=text[:12000])}],
    )
    if cfg["effort"]:
        kwargs["reasoning_effort"] = cfg["effort"]

    start = time.time()
    try:
        resp = client.chat.completions.create(**kwargs)
        out["latency_s"] = round(time.time() - start, 2)

        usage = getattr(resp, "usage", None)
        if usage:
            out["prompt_tokens"] = usage.prompt_tokens
            out["completion_tokens"] = usage.completion_tokens
            details = getattr(usage, "completion_tokens_details", None)
            out["reasoning_tokens"] = getattr(details, "reasoning_tokens", "") or ""

        classification = json.loads(resp.choices[0].message.content).get(
            "classification", {})
        role = classification.get("role")
        if role not in VALID_ROLES:
            out["error"] = f"invalid role: {role!r}"
            return out
        out.update(role=role,
                   confidence=classification.get("confidence", ""),
                   evidence_quote=classification.get("evidence_quote", ""),
                   reasoning=classification.get("reasoning", ""))
    except Exception as e:  # keep going; the error is recorded in the CSV
        out["latency_s"] = round(time.time() - start, 2)
        out["error"] = str(e)[:300]
    return out


def already_done(path):
    if not os.path.exists(path):
        return set()
    with open(path, newline="") as f:
        return {r["url"] for r in csv.DictReader(f) if not r.get("error")}


def run_config(tag, cfg, rows, workers):
    os.makedirs(OUT_DIR, exist_ok=True)
    path = os.path.join(OUT_DIR, f"{tag}.csv")
    done = already_done(path)
    todo = [r for r in rows if r[0] not in done]
    label = f"{cfg['model']}" + (f" / reasoning={cfg['effort']}" if cfg["effort"] else "")
    print(f"\n=== {tag}  ({label}) ===  {len(todo)} to run, {len(done)} already done")
    if not todo:
        return

    is_new = not os.path.exists(path)
    with open(path, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        if is_new:
            writer.writeheader()
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(classify_one, cfg, r) for r in todo]
            for i, fut in enumerate(as_completed(futures), 1):
                res = fut.result()
                writer.writerow(res)
                f.flush()
                status = res["role"] or f"ERROR {res['error'][:60]}"
                print(f"[{i}/{len(todo)}] {res['title'][:55]:55} -> {status}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--configs", nargs="+", default=list(CONFIGS),
                    choices=list(CONFIGS), help="which configs to run")
    ap.add_argument("--labeled-only", action="store_true",
                    help="only articles you've hand-labeled (articles.review is set)")
    ap.add_argument("--from-candidates", action="store_true",
                    help="only articles whose url appears in the candidates table")
    ap.add_argument("--limit", type=int, default=None, help="cap article count (smoke test)")
    ap.add_argument("--workers", type=int, default=4, help="parallel API calls")
    args = ap.parse_args()

    con = sqlite3.connect("labs.db")
    sql = ("SELECT url, institution, feed_name, category, title, full_text "
           "FROM articles WHERE full_text IS NOT NULL AND full_text<>''")
    if args.labeled_only:
        sql += " AND review IS NOT NULL AND review<>''"
    if args.from_candidates:
        sql += " AND url IN (SELECT article_url FROM candidates)"
    sql += " ORDER BY url"
    if args.limit:
        sql += f" LIMIT {int(args.limit)}"
    rows = con.execute(sql).fetchall()
    con.close()
    print(f"{len(rows)} articles selected")

    for tag in args.configs:  # order given: nano, then luna high -> medium -> low
        run_config(tag, CONFIGS[tag], rows, args.workers)

    print("\nDone. Now run: python compare_models.py")


if __name__ == "__main__":
    main()