"""
03_clean_and_load.py

Reads the messy raw spreadsheet export and:
  1. Cleans and standardizes every problematic field.
  2. Normalizes the data into a proper relational schema.
  3. Loads it into a SQLite database (db/graveyard.db).
  4. Prints a data-quality report summarizing exactly what was fixed --
     this report is itself part of the portfolio deliverable, since being
     able to show and explain a cleaning process is a core analyst skill.

SCHEMA
------
dim_category(category_id PK, category_name)
dim_barrier(barrier_id PK, barrier_name)
intentions(
    intention_id PK, title, category_id FK, motivation, date_created,
    perceived_importance, urgency, personal_interest, career_relevance,
    estimated_effort_hours, has_deadline, deadline_date
)
intention_events(
    event_id PK, intention_id FK, event_date, event_type, hours_spent, note
)
intention_barriers(intention_id FK, barrier_id FK)   -- bridge, composite PK
"""

import pandas as pd
import numpy as np
import sqlite3
import re
from datetime import datetime

pd.set_option("mode.chained_assignment", None)

raw = pd.read_csv("data/raw/intention_log_raw_export.csv")
n_raw_rows = len(raw)
issues = {}

# ---------------------------------------------------------------------------
# 1. TRIM / DEDUPLICATE EXACT DUPLICATE ROWS
# ---------------------------------------------------------------------------
before = len(raw)
raw = raw.drop_duplicates(subset=[c for c in raw.columns if c != "log_id"])
issues["exact_duplicate_rows_removed"] = before - len(raw)

# ---------------------------------------------------------------------------
# 2. CLEAN TEXT FIELDS: title, category, event_type, has_deadline
# ---------------------------------------------------------------------------
raw["title"] = raw["title"].astype(str).str.strip()
raw["title"] = raw["title"].apply(lambda t: t[0].upper() + t[1:] if t else t)

CATEGORY_MAP = {
    "career": "Career",
    "learning & skills": "Learning & Skills", "learning and skills": "Learning & Skills",
    "learning&skills": "Learning & Skills",
    "fitness & health": "Fitness & Health", "fitness/health": "Fitness & Health",
    "fitness and health": "Fitness & Health",
    "creative": "Creative", "creativity": "Creative",
    "financial": "Financial", "finance": "Financial",
    "home & admin": "Home & Admin", "home/admin": "Home & Admin", "home and admin": "Home & Admin",
    "relationships": "Relationships", "relationship": "Relationships",
    "travel": "Travel",
    "side project": "Side Project", "sideproject": "Side Project",
    "hobby": "Hobby", "hobbies": "Hobby",
}
raw["category_clean"] = raw["category"].astype(str).str.strip().str.lower().map(CATEGORY_MAP)
issues["category_values_unmapped"] = int(raw["category_clean"].isna().sum())
raw["category_clean"] = raw["category_clean"].fillna("Unknown")

EVENT_MAP = {
    "created": "CREATED", "new": "CREATED",
    "researched": "RESEARCHED", "researching": "RESEARCHED", "research": "RESEARCHED",
    "planned": "PLANNED", "planning": "PLANNED",
    "started": "STARTED", "start": "STARTED", "began": "STARTED",
    "continued": "CONTINUED", "continued work": "CONTINUED", "worked on it": "CONTINUED",
    "postponed": "POSTPONED", "pushed back": "POSTPONED", "delayed": "POSTPONED",
    "abandoned": "ABANDONED", "gave up": "ABANDONED",
    "completed": "COMPLETED", "done": "COMPLETED", "done!": "COMPLETED", "finished": "COMPLETED",
    "replaced": "REPLACED", "replaced by something else": "REPLACED",
}
raw["event_type_clean"] = raw["event_type"].astype(str).str.strip().str.lower().map(EVENT_MAP)
issues["event_type_values_unmapped"] = int(raw["event_type_clean"].isna().sum())
raw = raw.dropna(subset=["event_type_clean"])  # can't analyze an event with no valid type

DEADLINE_TRUE = {"y", "yes", "true", "1"}
DEADLINE_FALSE = {"n", "no", "false", "0", ""}
def parse_bool(v):
    s = str(v).strip().lower()
    if s in DEADLINE_TRUE:
        return True
    if s in DEADLINE_FALSE or s == "nan":
        return False
    return np.nan
raw["has_deadline_clean"] = raw["has_deadline"].apply(parse_bool)
issues["has_deadline_unparsed_defaulted_false"] = int(raw["has_deadline_clean"].isna().sum())
raw["has_deadline_clean"] = raw["has_deadline_clean"].fillna(False)

# ---------------------------------------------------------------------------
# 3. PARSE MIXED DATE FORMATS
# ---------------------------------------------------------------------------
DATE_FORMATS = ["%Y-%m-%d", "%d/%m/%Y", "%m-%d-%Y", "%d %b %Y", "%Y/%m/%d"]

def parse_messy_date(s):
    if pd.isna(s) or str(s).strip() == "":
        return pd.NaT
    s = str(s).strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return pd.to_datetime(s, errors="coerce")  # last resort

raw["event_date_clean"] = raw["event_date"].apply(parse_messy_date)
raw["date_created_clean"] = raw["date_created"].apply(parse_messy_date)
raw["deadline_date_clean"] = pd.to_datetime(raw["deadline_date"], errors="coerce")

issues["event_dates_unparseable"] = int(raw["event_date_clean"].isna().sum())
raw = raw.dropna(subset=["event_date_clean"])  # an event with no date can't be analyzed

# Fix impossible ordering: event_date before date_created -> use the earlier
# of the two as date_created (data entry swap), flag it.
bad_order_mask = raw["event_date_clean"] < raw["date_created_clean"]
issues["events_before_creation_date_fixed"] = int(bad_order_mask.sum())
raw.loc[bad_order_mask, "date_created_clean"] = raw.loc[bad_order_mask, "event_date_clean"]

# ---------------------------------------------------------------------------
# 4. CLEAN NUMERIC FIELDS
# ---------------------------------------------------------------------------
WORD_TO_NUM = {"very low": 1, "low": 2, "medium": 3, "high": 4, "very high": 5}

def clean_scale(v):
    if pd.isna(v):
        return np.nan
    s = str(v).strip().lower()
    if s in WORD_TO_NUM:
        return WORD_TO_NUM[s]
    try:
        n = float(v)
        return n if 1 <= n <= 5 else np.nan
    except (ValueError, TypeError):
        return np.nan

for col in ["perceived_importance", "urgency", "personal_interest", "career_relevance"]:
    raw[col + "_clean"] = raw[col].apply(clean_scale)

# hours_spent: fix negative typos (take absolute value) and cap extreme outliers
# (values > 60 hours in a single logged session are treated as data-entry errors
# and capped at a generous but plausible ceiling, flagged rather than silently kept)
hours = pd.to_numeric(raw["hours_spent"], errors="coerce")
neg_mask = hours < 0
issues["negative_hours_spent_fixed"] = int(neg_mask.sum())
hours = hours.abs()

outlier_mask = hours > 60
issues["extreme_hours_outliers_capped"] = int(outlier_mask.sum())
hours = hours.clip(upper=60)
raw["hours_spent_clean"] = hours.fillna(0.0)

# estimated_effort_hours: similar outlier guard (cap at a generous 400 hours)
eff = pd.to_numeric(raw["estimated_effort_hours"], errors="coerce")
raw["estimated_effort_hours_clean"] = eff.clip(lower=0.1, upper=400)

# ---------------------------------------------------------------------------
# 5. BUILD NORMALIZED TABLES
# ---------------------------------------------------------------------------

# --- dim_category ---
categories = sorted(raw["category_clean"].unique())
dim_category = pd.DataFrame({"category_id": range(1, len(categories) + 1), "category_name": categories})
cat_lookup = dim_category.set_index("category_name")["category_id"]

# --- intentions (one row per intention_id, take first non-null per field) ---
def first_valid(s):
    s = s.dropna()
    return s.iloc[0] if len(s) else np.nan

intentions_clean = raw.groupby("intention_id").agg(
    title=("title", "first"),
    category_name=("category_clean", "first"),
    motivation=("motivation", "first"),
    date_created=("date_created_clean", "min"),
    perceived_importance=("perceived_importance_clean", first_valid),
    urgency=("urgency_clean", first_valid),
    personal_interest=("personal_interest_clean", first_valid),
    career_relevance=("career_relevance_clean", first_valid),
    estimated_effort_hours=("estimated_effort_hours_clean", first_valid),
    has_deadline=("has_deadline_clean", "max"),
    deadline_date=("deadline_date_clean", first_valid),
).reset_index()

issues["missing_perceived_importance_after_cleaning"] = int(intentions_clean["perceived_importance"].isna().sum())
issues["missing_urgency_after_cleaning"] = int(intentions_clean["urgency"].isna().sum())
issues["missing_personal_interest_after_cleaning"] = int(intentions_clean["personal_interest"].isna().sum())
issues["missing_career_relevance_after_cleaning"] = int(intentions_clean["career_relevance"].isna().sum())

intentions_clean["category_id"] = intentions_clean["category_name"].map(cat_lookup)
intentions_clean = intentions_clean.drop(columns=["category_name"])

# --- intention_events (every remaining row after cleaning) ---
intention_events = raw[[
    "intention_id", "event_date_clean", "event_type_clean", "hours_spent_clean", "note"
]].rename(columns={
    "event_date_clean": "event_date", "event_type_clean": "event_type", "hours_spent_clean": "hours_spent"
}).reset_index(drop=True)
intention_events.insert(0, "event_id", range(1, len(intention_events) + 1))
intention_events["note"] = intention_events["note"].fillna("")

# --- dim_barrier + intention_barriers (parsed out of the note field on
#     ABANDONED/POSTPONED events, where a barrier reason was logged) ---
KNOWN_BARRIERS = [
    "Lack of time", "Lack of money", "Lack of motivation", "Unclear next step",
    "Perfectionism / fear of failure", "Competing priorities", "Lost interest",
    "Blocked by dependency", "Low energy / burnout", "No accountability",
    "Overestimated effort required",
]
dim_barrier = pd.DataFrame({"barrier_id": range(1, len(KNOWN_BARRIERS) + 1), "barrier_name": KNOWN_BARRIERS})
barrier_lookup = dim_barrier.set_index("barrier_name")["barrier_id"]

barrier_events = intention_events[intention_events["note"].isin(KNOWN_BARRIERS)]
intention_barriers = barrier_events[["intention_id", "note"]].drop_duplicates()
intention_barriers["barrier_id"] = intention_barriers["note"].map(barrier_lookup)
intention_barriers = intention_barriers[["intention_id", "barrier_id"]].drop_duplicates().reset_index(drop=True)

# ---------------------------------------------------------------------------
# 6. LOAD INTO SQLITE
# ---------------------------------------------------------------------------
conn = sqlite3.connect("db/graveyard.db")

dim_category.to_sql("dim_category", conn, if_exists="replace", index=False)
dim_barrier.to_sql("dim_barrier", conn, if_exists="replace", index=False)
intentions_clean.to_sql("intentions", conn, if_exists="replace", index=False)
intention_events.to_sql("intention_events", conn, if_exists="replace", index=False)
intention_barriers.to_sql("intention_barriers", conn, if_exists="replace", index=False)

conn.execute("""
    CREATE INDEX IF NOT EXISTS idx_events_intention ON intention_events(intention_id);
""")
conn.execute("""
    CREATE INDEX IF NOT EXISTS idx_intentions_category ON intentions(category_id);
""")
conn.commit()

# Also save flat cleaned CSVs for the Python/EDA stage and BI tools
intentions_clean.to_csv("data/clean/intentions.csv", index=False)
intention_events.to_csv("data/clean/intention_events.csv", index=False)
intention_barriers.to_csv("data/clean/intention_barriers.csv", index=False)
dim_category.to_csv("data/clean/dim_category.csv", index=False)
dim_barrier.to_csv("data/clean/dim_barrier.csv", index=False)

conn.close()

# ---------------------------------------------------------------------------
# 7. DATA QUALITY REPORT
# ---------------------------------------------------------------------------
print("=" * 60)
print("DATA CLEANING REPORT")
print("=" * 60)
print(f"Raw rows read:                 {n_raw_rows}")
print(f"Rows after cleaning (events):  {len(intention_events)}")
print(f"Intentions loaded:             {len(intentions_clean)}")
print("-" * 60)
for k, v in issues.items():
    print(f"{k:45s}: {v}")
print("=" * 60)
print("Loaded into db/graveyard.db")
print("Tables: dim_category, dim_barrier, intentions, intention_events, intention_barriers")

with open("data/clean/cleaning_report.txt", "w") as f:
    f.write("DATA CLEANING REPORT\n")
    f.write("=" * 60 + "\n")
    f.write(f"Raw rows read:                 {n_raw_rows}\n")
    f.write(f"Rows after cleaning (events):  {len(intention_events)}\n")
    f.write(f"Intentions loaded:             {len(intentions_clean)}\n")
    f.write("-" * 60 + "\n")
    for k, v in issues.items():
        f.write(f"{k:45s}: {v}\n")
