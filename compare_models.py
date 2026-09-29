"""Compare every results/<config>.csv against your human labels and against each other.

Writes:
    model_comparison.csv     one row per article, one role column per config
    model_disagreements.csv  only articles where a config disagrees with you,
                             or where the configs disagree with each other
"""
import glob
import os
import sqlite3

import pandas as pd

pd.set_option("display.max_colwidth", 50)
pd.set_option("display.width", 220)

RESULTS_DIR = "results"
PREFERRED_ORDER = ["nano", "luna_high", "luna_medium", "luna_low"]

paths = glob.glob(os.path.join(RESULTS_DIR, "*.csv"))
if not paths:
    raise SystemExit("No files in results/. Run classify_experiment.py first.")

tags = sorted((os.path.splitext(os.path.basename(p))[0] for p in paths),
              key=lambda t: PREFERRED_ORDER.index(t) if t in PREFERRED_ORDER else 99)

con = sqlite3.connect("labs.db")
articles = pd.read_sql("SELECT url, title, review AS human_label FROM articles", con)
con.close()
articles["human_label"] = articles["human_label"].replace("", pd.NA)

runs = {}
for tag in tags:
    df = pd.read_csv(os.path.join(RESULTS_DIR, f"{tag}.csv"))
    runs[tag] = df.drop_duplicates("url", keep="last")  # a retry replaces an earlier error

# ---- wide table: one row per article --------------------------------------
wide = articles.copy()
for tag, df in runs.items():
    sub = df[["url", "role", "confidence", "reasoning"]].rename(columns={
        "role": f"role_{tag}", "confidence": f"conf_{tag}", "reasoning": f"why_{tag}"})
    wide = wide.merge(sub, on="url", how="left")
role_cols = [f"role_{t}" for t in tags]
wide = wide[wide[role_cols].notna().any(axis=1)].copy()  # only articles that were run

# ---- summary per config ----------------------------------------------------
summary = []
labeled = wide[wide["human_label"].notna()]
for tag, df in runs.items():
    col = f"role_{tag}"
    lab = labeled[labeled["url"].isin(df["url"])]  # labeled articles this config attempted
    correct = (lab[col] == lab["human_label"]).sum()
    summary.append({
        "config": tag,
        "classified": int(df["role"].notna().sum()),
        "errors": int(df["role"].isna().sum()),
        "labeled_seen": len(lab),
        "agree_w_human": f"{correct}/{len(lab)}",
        "agree_%": round(100 * correct / len(lab), 1) if len(lab) else None,
        "avg_latency_s": round(df["latency_s"].mean(), 1),
        "avg_out_tokens": round(df["completion_tokens"].mean()),
        "avg_reasoning_tokens": (round(df["reasoning_tokens"].mean())
                                 if df["reasoning_tokens"].notna().any() else None),
        "n_prospective": int((df["role"] == "prospective").sum()),
        "n_facility": int((df["role"] == "facility").sum()),
        "n_not_relevant": int((df["role"] == "not_relevant").sum()),
    })

print("=" * 110)
print("SUMMARY BY CONFIG  (errors count as wrong on labeled articles)")
print("=" * 110)
print(pd.DataFrame(summary).to_string(index=False))

# ---- labeled articles, side by side ---------------------------------------
print()
print("=" * 110)
print("YOUR HAND-LABELED ARTICLES: human vs each config   (* = disagrees with you)")
print("=" * 110)
view = labeled[["title", "human_label"] + role_cols].copy()
for c in role_cols:
    view[c] = [("" if pd.isna(v) else v) + ("" if (pd.isna(v) or v == h) else " *")
               for v, h in zip(view[c], view["human_label"])]
view["title"] = view["title"].str[:45]
view.columns = ["title", "human"] + tags
print(view.to_string(index=False))

# ---- disagreements ---------------------------------------------------------
def config_split(row):
    vals = {row[c] for c in role_cols if pd.notna(row[c])}
    return len(vals) > 1

wide["configs_disagree"] = wide.apply(config_split, axis=1)
wide["any_vs_human_wrong"] = wide.apply(
    lambda r: pd.notna(r["human_label"]) and any(
        pd.notna(r[c]) and r[c] != r["human_label"] for c in role_cols), axis=1)

dis = wide[wide["configs_disagree"] | wide["any_vs_human_wrong"]]
unlabeled_split = wide[wide["human_label"].isna() & wide["configs_disagree"]]

print()
print(f"Articles where configs disagree with each other: {int(wide['configs_disagree'].sum())} "
      f"(of which unlabeled: {len(unlabeled_split)})")
print("The unlabeled ones are the best candidates to hand-label next: "
      "they're the cases where model choice actually matters.")

wide.to_csv("model_comparison.csv", index=False)
dis.to_csv("model_disagreements.csv", index=False)
print(f"\nWrote model_comparison.csv ({len(wide)} rows) and "
      f"model_disagreements.csv ({len(dis)} rows)")