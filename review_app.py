import re
import sqlite3

import streamlit as st

from fetch import FACULTY_KEYWORDS, OTHER_KEYWORDS, OTHER_CATEGORIES

st.set_page_config(page_title="Lead review", layout="wide")
con = sqlite3.connect("labs.db", check_same_thread=False)

LABELS = ["new_lab", "prospective", "facility", "not_relevant"]


def clean(html):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html or "")).strip()


st.title("Review potential new-lab leads")
mode = st.sidebar.radio("Show", ["Unreviewed", "Reviewed", "All"])
where = "keyword_hit=1"
if mode == "Unreviewed":
    where += " AND (review IS NULL OR review='')"
elif mode == "Reviewed":
    where += " AND review IS NOT NULL AND review<>''"

rows = con.execute(
    "SELECT url, institution, feed_name, category, title, published, full_text, "
    f"summary, review, notes FROM articles WHERE {where} ORDER BY fetched_at DESC"
).fetchall()
st.sidebar.write(f"{len(rows)} articles")
if not rows:
    st.success("Nothing to show.")
    st.stop()

choice = st.sidebar.selectbox(
    "Article", range(len(rows)),
    format_func=lambda i: f"{rows[i][1]} | {rows[i][4][:55]}")
url, inst, feed, cat, title, pub, full, summ, review, notes = rows[choice]

st.subheader(title)
st.caption(f"{inst} / {feed} · {cat} · {pub}")
st.link_button("Open original article", url)

pattern = OTHER_KEYWORDS if cat in OTHER_CATEGORIES else FACULTY_KEYWORDS
text = full if full else clean(summ)
if not full:
    st.warning("Full text unavailable, showing the RSS summary only.")
st.markdown(pattern.sub(lambda m: f":orange[**{m.group(0)}**]", text[:8000]))

st.divider()
label = st.radio("Verdict", LABELS, horizontal=True,
                 index=LABELS.index(review) if review in LABELS else None)
note = st.text_input("Notes (PI name, why, etc.)", value=notes or "")
if st.button("Save") and label:
    con.execute("UPDATE articles SET review=?, notes=? WHERE url=?", (label, note, url))
    con.commit()
    st.rerun()