"""
01_generate_synthetic_data.py

Generates a synthetic "Graveyard of Good Intentions" dataset: a personal log
of intentions (goals, tasks, projects people intend to do) and the events
that happen to them over time (researched, started, postponed, abandoned,
completed, etc.)

DESIGN NOTE ON REALISM:
This does not sample outcomes randomly. Each intention has underlying traits
(personal interest, perceived importance, estimated effort, whether it has a
deadline, category) that probabilistically influence its outcome through a
noisy scoring function -- similar to how these things plausibly interact in
real life, but with enough noise that no relationship is perfectly clean.
This avoids "manufactured" correlations that would make the later analysis
look artificially tidy.

The script outputs a single denormalized CSV that mimics what a person would
actually produce if they logged this by hand in a spreadsheet over ~2 years:
inconsistent capitalization, mixed date formats, some missing values, a few
typos and out-of-range entries, and duplicate rows. This "raw" file is the
deliberately messy starting point for the cleaning/ETL script
(02_clean_and_load.py), which is a normal and expected part of a real
analytics project.
"""

import numpy as np
import pandas as pd
from datetime import datetime, timedelta
import random

RNG_SEED = 42
random.seed(RNG_SEED)
np.random.seed(RNG_SEED)

N_INTENTIONS = 320
PROJECT_START = datetime(2023, 1, 1)
PROJECT_END = datetime(2025, 8, 1)
TOTAL_DAYS = (PROJECT_END - PROJECT_START).days

# ---------------------------------------------------------------------------
# REFERENCE DATA
# ---------------------------------------------------------------------------

CATEGORIES = [
    "Career", "Learning & Skills", "Fitness & Health", "Creative",
    "Financial", "Home & Admin", "Relationships", "Travel",
    "Side Project", "Hobby",
]

MOTIVATIONS = [
    "Career advancement", "Health & wellbeing", "Personal growth",
    "Financial security", "Social connection", "Curiosity / fun",
    "Obligation / should-do", "Creative expression",
]

BARRIERS = [
    "Lack of time", "Lack of money", "Lack of motivation",
    "Unclear next step", "Perfectionism / fear of failure",
    "Competing priorities", "Lost interest", "Blocked by dependency",
    "Low energy / burnout", "No accountability", "Overestimated effort required",
]

EVENT_TYPES = [
    "CREATED", "RESEARCHED", "PLANNED", "STARTED",
    "CONTINUED", "POSTPONED", "ABANDONED", "COMPLETED", "REPLACED",
]

# A bank of realistic, generic intention titles per category (not tied to
# any one person) -- enough variety to avoid obvious repetition.
TITLE_BANK = {
    "Career": [
        "Update CV and LinkedIn profile", "Apply to 10 jobs abroad",
        "Get a professional certification", "Network with 5 people in target industry",
        "Prepare for technical interviews", "Ask for a performance review",
        "Research career change options", "Build a portfolio website",
        "Learn salary negotiation", "Find a mentor in my field",
    ],
    "Learning & Skills": [
        "Learn SQL properly", "Finish an online Python course",
        "Learn conversational Spanish", "Read one book on statistics",
        "Learn to use Power BI", "Complete a data visualization course",
        "Learn touch typing", "Study for a certification exam",
        "Learn basic public speaking", "Practice a new software tool weekly",
    ],
    "Fitness & Health": [
        "Start going to the gym 3x/week", "Train for a 5k run",
        "Improve sleep schedule", "Cut down on sugar",
        "Start a home workout routine", "Book a full medical check-up",
        "Start daily stretching", "Learn to cook healthier meals",
        "Reduce screen time before bed", "Start meditating daily",
    ],
    "Creative": [
        "Finish a painting series", "Write short stories weekly",
        "Learn to play an instrument", "Start a photography project",
        "Redesign a personal art portfolio", "Try a new craft technique",
        "Enter a local art competition", "Start sketching daily",
        "Learn a new design software", "Restore an old creative project",
    ],
    "Financial": [
        "Build an emergency fund", "Create a monthly budget",
        "Review and cut subscriptions", "Research investment options",
        "Pay off a small debt", "Set up automatic savings",
        "Compare insurance providers", "Track spending for a month",
        "Learn the basics of investing", "Plan a savings goal",
    ],
    "Home & Admin": [
        "Declutter the apartment", "Organize digital files",
        "Renew an expiring document", "Deep clean the kitchen",
        "Fix a recurring household issue", "Set up a filing system",
        "Sell unused items online", "Reorganize the wardrobe",
        "Update personal records", "Automate a recurring bill payment",
    ],
    "Relationships": [
        "Call an old friend", "Plan a family visit",
        "Write a long-overdue message", "Organize a small get-together",
        "Reconnect with a former colleague", "Plan a date night routine",
        "Send a thank-you note", "Schedule regular calls with family",
        "Repair a strained relationship", "Join a local social group",
    ],
    "Travel": [
        "Plan a solo trip", "Research a relocation destination",
        "Book a long-postponed trip", "Learn key phrases for a trip",
        "Plan a weekend getaway", "Research visa requirements",
        "Create a travel budget", "Plan a trip itinerary",
        "Research flights for a trip", "Plan a road trip route",
    ],
    "Side Project": [
        "Build a personal data project", "Start a small blog",
        "Build a portfolio project", "Prototype a small app idea",
        "Start a freelance side gig", "Build an automation script",
        "Launch a small online shop", "Start a niche newsletter",
        "Build a personal dashboard", "Contribute to an open-source project",
    ],
    "Hobby": [
        "Start a houseplant collection", "Learn basic woodworking",
        "Start journaling regularly", "Try a new recipe every week",
        "Start a puzzle-solving habit", "Learn basic calligraphy",
        "Start a small garden", "Collect and organize a hobby set",
        "Learn a card or board game deeply", "Start a reading challenge",
    ],
}

# ---------------------------------------------------------------------------
# HELPER FUNCTIONS
# ---------------------------------------------------------------------------


def random_date(start, end):
    delta = (end - start).days
    if delta <= 0:
        return start
    return start + timedelta(days=random.randint(0, delta))


def sigmoid(x):
    return 1 / (1 + np.exp(-x))


# ---------------------------------------------------------------------------
# GENERATE INTENTIONS (MASTER RECORDS)
# ---------------------------------------------------------------------------

intentions = []
used_titles = set()

for i in range(1, N_INTENTIONS + 1):
    category = random.choice(CATEGORIES)
    pool = [t for t in TITLE_BANK[category] if t not in used_titles]
    if not pool:
        pool = TITLE_BANK[category]
    title = random.choice(pool)
    used_titles.add(title)

    date_created = random_date(PROJECT_START, PROJECT_END - timedelta(days=30))

    perceived_importance = int(np.clip(np.random.normal(3.2, 1.1), 1, 5))
    urgency = int(np.clip(np.random.normal(2.6, 1.2), 1, 5))
    personal_interest = int(np.clip(np.random.normal(3.4, 1.2), 1, 5))
    career_relevance = int(np.clip(np.random.normal(2.5, 1.4), 1, 5)) if category in \
        ("Career", "Learning & Skills", "Side Project", "Financial") else int(np.clip(np.random.normal(1.6, 1.0), 1, 5))

    # Effort estimate: right-skewed (most things feel "quick", a few are huge)
    estimated_effort_hours = round(float(np.random.lognormal(mean=2.1, sigma=0.9)), 1)
    estimated_effort_hours = float(np.clip(estimated_effort_hours, 0.5, 400))

    has_deadline = random.random() < 0.28
    deadline_date = None
    if has_deadline:
        deadline_date = date_created + timedelta(days=random.randint(14, 200))

    motivation = random.choice(MOTIVATIONS)

    intentions.append({
        "intention_id": i,
        "title": title,
        "category": category,
        "motivation": motivation,
        "date_created": date_created,
        "perceived_importance": perceived_importance,
        "urgency": urgency,
        "personal_interest": personal_interest,
        "career_relevance": career_relevance,
        "estimated_effort_hours": estimated_effort_hours,
        "has_deadline": has_deadline,
        "deadline_date": deadline_date,
    })

intentions_df = pd.DataFrame(intentions)

# ---------------------------------------------------------------------------
# SCORE EACH INTENTION -> OUTCOME PROBABILITIES (WITH NOISE)
# ---------------------------------------------------------------------------
# This is deliberately a soft, noisy score -- not a deterministic rule -- so
# that the resulting dataset has realistic, moderate (not perfect)
# correlations for the analysis to discover.

def compute_scores(row):
    effort_penalty = np.log1p(row["estimated_effort_hours"]) * 0.35
    score = (
        0.55 * row["personal_interest"]
        + 0.35 * row["perceived_importance"]
        + 0.25 * row["urgency"]
        + 0.15 * row["career_relevance"]
        + (0.6 if row["has_deadline"] else 0.0)
        - effort_penalty
        + np.random.normal(0, 1.6)  # substantial noise
    )
    return score

intentions_df["_score"] = intentions_df.apply(compute_scores, axis=1)
# Normalize score to a 0-1 "momentum" probability via sigmoid
intentions_df["_momentum"] = sigmoid((intentions_df["_score"] - intentions_df["_score"].mean()) / intentions_df["_score"].std())

# ---------------------------------------------------------------------------
# GENERATE EVENT LOGS PER INTENTION
# ---------------------------------------------------------------------------

event_rows = []
log_id_counter = 1

for _, row in intentions_df.iterrows():
    iid = row["intention_id"]
    momentum = row["_momentum"]
    created = row["date_created"]
    cursor_date = created

    event_rows.append((log_id_counter, iid, row["title"], row["category"],
                        created, created, "CREATED", 0.0, ""))
    log_id_counter += 1

    # Probability gates for progressing through each stage, modulated by momentum
    p_research = 0.55 + 0.35 * momentum
    p_plan = 0.35 + 0.45 * momentum
    p_start = 0.25 + 0.55 * momentum
    p_complete_given_started = 0.15 + 0.55 * momentum

    stage_reached = "CREATED"
    researched_hours = 0.0
    postpone_count = 0
    continued_count = 0

    # RESEARCHED (0-4 sessions)
    if random.random() < p_research:
        n_research = np.random.choice([1, 2, 3, 4], p=[0.45, 0.3, 0.15, 0.10])
        for _ in range(n_research):
            cursor_date = cursor_date + timedelta(days=random.randint(1, 25))
            if cursor_date > PROJECT_END:
                break
            hrs = round(float(np.random.exponential(1.3)) + 0.2, 1)
            researched_hours += hrs
            event_rows.append((log_id_counter, iid, row["title"], row["category"],
                                created, cursor_date, "RESEARCHED", hrs, ""))
            log_id_counter += 1
        stage_reached = "RESEARCHED"

        # occasional postponement right after researching
        if random.random() < (0.5 - 0.3 * momentum):
            cursor_date = cursor_date + timedelta(days=random.randint(3, 30))
            if cursor_date <= PROJECT_END:
                postpone_count += 1
                barrier_note = random.choice(BARRIERS)
                event_rows.append((log_id_counter, iid, row["title"], row["category"],
                                    created, cursor_date, "POSTPONED", 0.0, barrier_note))
                log_id_counter += 1

    # PLANNED
    if stage_reached == "RESEARCHED" and random.random() < p_plan:
        cursor_date = cursor_date + timedelta(days=random.randint(1, 20))
        if cursor_date <= PROJECT_END:
            event_rows.append((log_id_counter, iid, row["title"], row["category"],
                                created, cursor_date, "PLANNED", 0.0, ""))
            log_id_counter += 1
            stage_reached = "PLANNED"

    # STARTED
    if stage_reached == "PLANNED" and random.random() < p_start:
        cursor_date = cursor_date + timedelta(days=random.randint(1, 30))
        if cursor_date <= PROJECT_END:
            event_rows.append((log_id_counter, iid, row["title"], row["category"],
                                created, cursor_date, "STARTED", 0.0, ""))
            log_id_counter += 1
            stage_reached = "STARTED"

            # CONTINUED sessions (work sessions after starting)
            n_continue = np.random.poisson(1.5 + 3.0 * momentum)
            for _ in range(n_continue):
                cursor_date = cursor_date + timedelta(days=random.randint(2, 35))
                if cursor_date > PROJECT_END:
                    break
                hrs = round(float(np.random.exponential(2.2)) + 0.3, 1)
                event_rows.append((log_id_counter, iid, row["title"], row["category"],
                                    created, cursor_date, "CONTINUED", hrs, ""))
                log_id_counter += 1
                continued_count += 1
                # chance of a postponement between sessions
                if random.random() < (0.30 - 0.15 * momentum):
                    cursor_date = cursor_date + timedelta(days=random.randint(5, 40))
                    if cursor_date <= PROJECT_END:
                        postpone_count += 1
                        barrier_note = random.choice(BARRIERS)
                        event_rows.append((log_id_counter, iid, row["title"], row["category"],
                                            created, cursor_date, "POSTPONED", 0.0, barrier_note))
                        log_id_counter += 1

    # TERMINAL OUTCOME
    if stage_reached == "STARTED":
        if random.random() < p_complete_given_started:
            cursor_date = cursor_date + timedelta(days=random.randint(1, 25))
            if cursor_date <= PROJECT_END:
                event_rows.append((log_id_counter, iid, row["title"], row["category"],
                                    created, cursor_date, "COMPLETED", 0.0, ""))
                log_id_counter += 1
        else:
            # abandoned, replaced, or left open (zombie) -- weighted by momentum
            outcome_roll = random.random()
            if outcome_roll < 0.55 - 0.2 * momentum:
                cursor_date = cursor_date + timedelta(days=random.randint(5, 60))
                if cursor_date <= PROJECT_END:
                    barrier_note = random.choice(BARRIERS)
                    event_rows.append((log_id_counter, iid, row["title"], row["category"],
                                        created, cursor_date, "ABANDONED", 0.0, barrier_note))
                    log_id_counter += 1
            elif outcome_roll < 0.70 - 0.1 * momentum:
                cursor_date = cursor_date + timedelta(days=random.randint(5, 60))
                if cursor_date <= PROJECT_END:
                    event_rows.append((log_id_counter, iid, row["title"], row["category"],
                                        created, cursor_date, "REPLACED", 0.0, "Replaced by a different priority"))
                    log_id_counter += 1
            # else: left open / stalled -- no terminal event (a "zombie" intention)
    elif stage_reached in ("PLANNED", "RESEARCHED"):
        # never actually started -- often abandoned, replaced, or just stalls silently
        outcome_roll = random.random()
        if outcome_roll < 0.35:
            cursor_date = cursor_date + timedelta(days=random.randint(10, 90))
            if cursor_date <= PROJECT_END:
                barrier_note = random.choice(BARRIERS)
                event_rows.append((log_id_counter, iid, row["title"], row["category"],
                                    created, cursor_date, "ABANDONED", 0.0, barrier_note))
                log_id_counter += 1
        elif outcome_roll < 0.45:
            cursor_date = cursor_date + timedelta(days=random.randint(10, 90))
            if cursor_date <= PROJECT_END:
                event_rows.append((log_id_counter, iid, row["title"], row["category"],
                                    created, cursor_date, "REPLACED", 0.0, "Replaced by a different priority"))
                log_id_counter += 1
        # else: stalls silently (zombie candidate)
    else:
        # never even researched -- mostly just quietly forgotten (no further events)
        pass

event_log_df = pd.DataFrame(
    event_rows,
    columns=["log_id", "intention_id", "title", "category", "date_created",
             "event_date", "event_type", "hours_spent", "note"]
)

print(f"Generated {len(intentions_df)} intentions and {len(event_log_df)} events.")
print(event_log_df["event_type"].value_counts())

# ---------------------------------------------------------------------------
# ATTACH BARRIERS (for intentions that stalled/were abandoned) -- separate table
# ---------------------------------------------------------------------------

barrier_rows = []
non_completed_ids = set(intentions_df["intention_id"]) - set(
    event_log_df.loc[event_log_df["event_type"] == "COMPLETED", "intention_id"]
)
for iid in non_completed_ids:
    if random.random() < 0.75:  # not every stalled intention has a logged reason
        n_barriers = random.choice([1, 1, 2, 2, 3])
        chosen = random.sample(BARRIERS, k=min(n_barriers, len(BARRIERS)))
        for b in chosen:
            barrier_rows.append({"intention_id": iid, "barrier": b})

barriers_df = pd.DataFrame(barrier_rows)

# ---------------------------------------------------------------------------
# DEPENDENCIES (a subset of intentions depend on another intention finishing)
# ---------------------------------------------------------------------------

dependency_rows = []
ids = list(intentions_df["intention_id"])
n_dependencies = 35
attempts = 0
seen_pairs = set()
while len(dependency_rows) < n_dependencies and attempts < 500:
    attempts += 1
    a, b = random.sample(ids, 2)
    # dependency must respect creation order (a depends on b, b created no later than a)
    ca = intentions_df.loc[intentions_df.intention_id == a, "date_created"].iloc[0]
    cb = intentions_df.loc[intentions_df.intention_id == b, "date_created"].iloc[0]
    if cb <= ca and (a, b) not in seen_pairs and a != b:
        dependency_rows.append({"intention_id": a, "depends_on_intention_id": b})
        seen_pairs.add((a, b))

dependencies_df = pd.DataFrame(dependency_rows)

# ---------------------------------------------------------------------------
# SAVE THE "CLEAN GROUND TRUTH" REFERENCE TABLES (used later for comparison,
# not the deliverable itself -- the deliverable is the messy raw export below)
# ---------------------------------------------------------------------------

intentions_df.drop(columns=["_score", "_momentum"]).to_csv(
    "data/clean/_ground_truth_intentions.csv", index=False
)
event_log_df.to_csv("data/clean/_ground_truth_events.csv", index=False)
barriers_df.to_csv("data/clean/_ground_truth_barriers.csv", index=False)
dependencies_df.to_csv("data/clean/_ground_truth_dependencies.csv", index=False)

print("Ground truth tables saved to data/clean/ (prefixed with _ -- for reference only).")
