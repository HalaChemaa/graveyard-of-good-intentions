"""
02_make_messy_raw_export.py

Takes the clean ground-truth tables and produces a single denormalized CSV
that mimics what this data would actually look like if a person logged it
by hand in a spreadsheet over ~2.5 years: inconsistent capitalization, mixed
date formats, missing values, a few typos, duplicate rows, and some
impossible values that need to be caught during cleaning.

This messy file (data/raw/intention_log_raw_export.csv) is the ONLY input
the cleaning/ETL script (03_clean_and_load.py) is allowed to use -- it does
not get to see the ground-truth tables. This mirrors a real project, where
the analyst only has the messy export a person actually produced.
"""

import pandas as pd
import numpy as np
import random
from datetime import datetime

random.seed(7)
np.random.seed(7)

intentions = pd.read_csv("data/clean/_ground_truth_intentions.csv", parse_dates=["date_created", "deadline_date"])
events = pd.read_csv("data/clean/_ground_truth_events.csv", parse_dates=["date_created", "event_date"])
barriers = pd.read_csv("data/clean/_ground_truth_barriers.csv")

# Merge intention-level attributes onto every event row (this is exactly how
# someone would build a single flat log in a spreadsheet -- re-typing the
# same intention info on every row, which is itself a source of
# inconsistency).
merged = events.merge(
    intentions[["intention_id", "motivation", "perceived_importance", "urgency",
                "personal_interest", "career_relevance", "estimated_effort_hours",
                "has_deadline", "deadline_date"]],
    on="intention_id", how="left"
)

# Attach a barrier note where relevant (join first matching barrier, if any)
first_barrier = barriers.drop_duplicates(subset="intention_id", keep="first").set_index("intention_id")["barrier"]
merged["barrier_lookup"] = merged["intention_id"].map(first_barrier)
merged.loc[merged["note"] == "", "note"] = merged.loc[merged["note"] == "", "barrier_lookup"].where(
    merged["event_type"].isin(["ABANDONED", "POSTPONED"]), ""
)
merged.drop(columns=["barrier_lookup"], inplace=True)
merged["note"] = merged["note"].fillna("")

raw = merged.copy()

# ---------------------------------------------------------------------------
# MESSINESS INJECTION
# ---------------------------------------------------------------------------

# 1. Category casing / whitespace inconsistency (category comes from
#    intentions table but let's re-derive a "category_raw" text column with
#    noise, since in the real spreadsheet this was free-typed each time)
CATEGORY_VARIANTS = {
    "Career": ["Career", "career", "CAREER", " Career", "Career "],
    "Learning & Skills": ["Learning & Skills", "learning and skills", "Learning&Skills", "LEARNING & SKILLS"],
    "Fitness & Health": ["Fitness & Health", "fitness/health", "Fitness and Health", "FITNESS & HEALTH"],
    "Creative": ["Creative", "creative", "CREATIVE ", "Creativity"],
    "Financial": ["Financial", "financial", "Finance", "FINANCIAL"],
    "Home & Admin": ["Home & Admin", "home/admin", "Home and Admin", "HOME & ADMIN"],
    "Relationships": ["Relationships", "relationships", "Relationship", "RELATIONSHIPS"],
    "Travel": ["Travel", "travel", "TRAVEL ", " Travel"],
    "Side Project": ["Side Project", "side project", "SideProject", "SIDE PROJECT"],
    "Hobby": ["Hobby", "hobby", "HOBBY", "Hobbies"],
}

# category is stored on the intentions table originally; carry it via events
cat_map = intentions.set_index("intention_id")["category"]
raw["category"] = raw["intention_id"].map(cat_map)
raw["category"] = raw["category"].apply(lambda c: random.choice(CATEGORY_VARIANTS.get(c, [c])))

# 2. event_type free-typed inconsistency
EVENT_VARIANTS = {
    "CREATED": ["Created", "created", "CREATED", "New"],
    "RESEARCHED": ["Researched", "researching", "RESEARCHED", "Research"],
    "PLANNED": ["Planned", "planning", "PLANNED"],
    "STARTED": ["Started", "start", "STARTED ", "Began"],
    "CONTINUED": ["Continued", "continued work", "CONTINUED", "worked on it"],
    "POSTPONED": ["Postponed", "postponed", "PUSHED BACK", "delayed"],
    "ABANDONED": ["Abandoned", "abandoned", "ABANDONED", "gave up"],
    "COMPLETED": ["Completed", "completed", "DONE", "Done!", "finished"],
    "REPLACED": ["Replaced", "replaced by something else", "REPLACED"],
}
raw["event_type_raw"] = raw["event_type"].apply(lambda e: random.choice(EVENT_VARIANTS[e]))

# 3. Mixed date formats for event_date (string formatting chaos)
def messy_date(d):
    if pd.isna(d):
        return ""
    fmt = random.choice(["%Y-%m-%d", "%d/%m/%Y", "%m-%d-%Y", "%d %b %Y", "%Y/%m/%d"])
    try:
        return d.strftime(fmt)
    except Exception:
        return str(d)

raw["event_date_raw"] = raw["event_date"].apply(messy_date)
raw["date_created_raw"] = raw["date_created"].apply(messy_date)

# 4. Missing values injected at random into several columns
for col, missing_rate in [
    ("perceived_importance", 0.06), ("urgency", 0.07), ("personal_interest", 0.05),
    ("career_relevance", 0.10), ("hours_spent", 0.08), ("estimated_effort_hours", 0.04),
]:
    mask = np.random.random(len(raw)) < missing_rate
    raw.loc[mask, col] = np.nan

# 5. A handful of importance/urgency/interest scores typed as words instead of numbers
WORD_SCALE = {1: "very low", 2: "low", 3: "medium", 4: "high", 5: "very high"}
for col in ["perceived_importance", "urgency", "personal_interest"]:
    raw[col] = raw[col].astype(object)
    idx = raw.sample(frac=0.03, random_state=random.randint(1, 9999)).index
    for i in idx:
        val = raw.at[i, col]
        if pd.notna(val):
            raw.at[i, col] = WORD_SCALE.get(int(val), val)

# 6. A few negative / impossible hours_spent typos (e.g. someone typed -2 instead of 2,
#    or an extra zero producing an absurd outlier)
neg_idx = raw.sample(frac=0.015, random_state=11).index
raw.loc[neg_idx, "hours_spent"] = -raw.loc[neg_idx, "hours_spent"].abs()

outlier_idx = raw.sample(frac=0.01, random_state=12).index
raw.loc[outlier_idx, "hours_spent"] = raw.loc[outlier_idx, "hours_spent"].abs() * 50 + 500

# 7. has_deadline stored inconsistently (Y/N/yes/no/TRUE/FALSE/blank)
DEADLINE_VARIANTS_TRUE = ["Y", "Yes", "yes", "TRUE", "True", "1"]
DEADLINE_VARIANTS_FALSE = ["N", "No", "no", "FALSE", "False", "0", ""]
raw["has_deadline_raw"] = raw["has_deadline"].apply(
    lambda x: random.choice(DEADLINE_VARIANTS_TRUE) if x else random.choice(DEADLINE_VARIANTS_FALSE)
)
missing_dl = np.random.random(len(raw)) < 0.05
raw.loc[missing_dl, "has_deadline_raw"] = ""

# 8. Duplicate a handful of rows (accidental double paste in spreadsheet)
dup_rows = raw.sample(frac=0.02, random_state=99)
raw = pd.concat([raw, dup_rows], ignore_index=True)

# 9. A few titles with trailing whitespace / inconsistent casing
def messy_title(t):
    if random.random() < 0.08:
        return t.upper()
    if random.random() < 0.08:
        return t.lower()
    if random.random() < 0.05:
        return " " + t + "  "
    return t

raw["title"] = raw["title"].apply(messy_title)

# 10. Shuffle row order (a real log wouldn't be perfectly sorted since it's
#     appended to across many separate sessions of editing the spreadsheet)
raw = raw.sample(frac=1.0, random_state=2024).reset_index(drop=True)
raw["log_id"] = range(1, len(raw) + 1)

# ---------------------------------------------------------------------------
# FINAL RAW COLUMN SELECTION / ORDERING (as if exported straight from Excel)
# ---------------------------------------------------------------------------

raw_export = raw[[
    "log_id", "intention_id", "title", "category", "motivation",
    "date_created_raw", "event_date_raw", "event_type_raw", "hours_spent",
    "perceived_importance", "urgency", "personal_interest", "career_relevance",
    "estimated_effort_hours", "has_deadline_raw", "deadline_date", "note",
]].rename(columns={
    "date_created_raw": "date_created",
    "event_date_raw": "event_date",
    "event_type_raw": "event_type",
    "has_deadline_raw": "has_deadline",
})

raw_export.to_csv("data/raw/intention_log_raw_export.csv", index=False)
print(f"Raw messy export saved: {len(raw_export)} rows -> data/raw/intention_log_raw_export.csv")
print("\nSample of the mess:")
print(raw_export.sample(8, random_state=1).to_string())
