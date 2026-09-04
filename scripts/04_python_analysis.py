"""
04_python_analysis.py

Core Python analysis for "The Graveyard of Good Intentions". Reads the
cleaned tables (produced by 03_clean_and_load.py), computes the project's
key metrics, runs the prioritized analytical questions, and saves charts +
a metrics summary CSV for use in the report / BI tools.

Libraries: pandas, numpy, matplotlib, seaborn (only where it genuinely helps
readability), scipy (for a couple of light statistical checks). No machine
learning -- this is deliberately a data-analyst project, not an ML project.
"""

import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import seaborn as sns
from scipy import stats
import sqlite3
import os

sns.set_style("whitegrid")
OUT = "outputs"
os.makedirs(OUT, exist_ok=True)

conn = sqlite3.connect("db/graveyard.db")
intentions = pd.read_sql("SELECT * FROM intentions", conn, parse_dates=["date_created", "deadline_date"])
events = pd.read_sql("SELECT * FROM intention_events", conn, parse_dates=["event_date"])
categories = pd.read_sql("SELECT * FROM dim_category", conn)
barriers_dim = pd.read_sql("SELECT * FROM dim_barrier", conn)
intention_barriers = pd.read_sql("SELECT * FROM intention_barriers", conn)
conn.close()

intentions = intentions.merge(categories, on="category_id", how="left")

OBS_END = pd.Timestamp("2025-08-01")

# ---------------------------------------------------------------------------
# DERIVE PER-INTENTION SUMMARY TABLE (this is the analytical backbone)
# ---------------------------------------------------------------------------

def summarize(group):
    types = group["event_type"]
    last_date = group["event_date"].max()
    first_date = group["event_date"].min()

    if (types == "COMPLETED").any():
        status = "COMPLETED"
        terminal_date = group.loc[types == "COMPLETED", "event_date"].iloc[0]
    elif (types == "ABANDONED").any():
        status = "ABANDONED"
        terminal_date = group.loc[types == "ABANDONED", "event_date"].iloc[0]
    elif (types == "REPLACED").any():
        status = "REPLACED"
        terminal_date = group.loc[types == "REPLACED", "event_date"].iloc[0]
    else:
        status = "OPEN/STALLED"
        terminal_date = last_date

    research_hours = group.loc[types == "RESEARCHED", "hours_spent"].sum()
    action_hours = group.loc[types == "CONTINUED", "hours_spent"].sum()
    n_postponed = (types == "POSTPONED").sum()
    n_continued = (types == "CONTINUED").sum()
    n_researched = (types == "RESEARCHED").sum()
    reached_started = (types == "STARTED").any()

    return pd.Series({
        "status": status,
        "first_event_date": first_date,
        "last_event_date": last_date,
        "terminal_date": terminal_date,
        "research_hours": research_hours,
        "action_hours": action_hours,
        "n_postponed": n_postponed,
        "n_continued_sessions": n_continued,
        "n_researched_sessions": n_researched,
        "reached_started": reached_started,
    })

per_intention = events.groupby("intention_id").apply(summarize, include_groups=False).reset_index()
master = intentions.merge(per_intention, on="intention_id", how="left")

master["survival_days"] = (master["terminal_date"] - master["date_created"]).dt.days
master["days_since_last_activity"] = (OBS_END - master["last_event_date"]).dt.days
master["action_latency_days"] = np.nan
started_mask = master["reached_started"] == True
# action latency: days between creation and STARTED event
started_events = events[events["event_type"] == "STARTED"][["intention_id", "event_date"]].rename(
    columns={"event_date": "started_date"}
)
master = master.merge(started_events, on="intention_id", how="left")
master["action_latency_days"] = (master["started_date"] - master["date_created"]).dt.days

master["is_zombie"] = (
    (master["status"] == "OPEN/STALLED")
    & ((master["research_hours"] > 0) | (master["action_hours"] > 0))
    & (master["days_since_last_activity"] > 120)
)

master["research_to_action_ratio"] = master["research_hours"] / master["action_hours"].replace(0, np.nan)
master["completion_efficiency"] = np.where(
    master["status"] == "COMPLETED",
    master["action_hours"] / master["estimated_effort_hours"],
    np.nan,
)

master.to_csv(f"{OUT}/master_intention_table.csv", index=False)

# ---------------------------------------------------------------------------
# METRIC 1: INTENTION CONVERSION RATE
# ---------------------------------------------------------------------------
n_total = len(master)
n_completed = (master["status"] == "COMPLETED").sum()
conversion_rate = n_completed / n_total

# ---------------------------------------------------------------------------
# METRIC 2: INTENTION SURVIVAL TIME (median days to terminal outcome/last activity)
# ---------------------------------------------------------------------------
median_survival = master["survival_days"].median()

# ---------------------------------------------------------------------------
# METRIC 3: RESEARCH-TO-ACTION RATIO (overall, not just per-intention)
# ---------------------------------------------------------------------------
overall_research_hours = master["research_hours"].sum()
overall_action_hours = master["action_hours"].sum()
overall_rta_ratio = overall_research_hours / overall_action_hours

# ---------------------------------------------------------------------------
# METRIC 4: POSTPONEMENT RATE (share of intentions postponed at least once)
# ---------------------------------------------------------------------------
postponement_rate = (master["n_postponed"] > 0).mean()

# ---------------------------------------------------------------------------
# METRIC 5: ZOMBIE INTENTION RATE
# ---------------------------------------------------------------------------
zombie_rate = master["is_zombie"].mean()

# ---------------------------------------------------------------------------
# METRIC 6: ACTION LATENCY (median days from creation to actually starting)
# ---------------------------------------------------------------------------
median_action_latency = master["action_latency_days"].median()

# ---------------------------------------------------------------------------
# METRIC 7: COMPLETION EFFICIENCY (actual/estimated hours, completed only)
# ---------------------------------------------------------------------------
median_completion_efficiency = master["completion_efficiency"].median()

metrics_summary = pd.DataFrame([
    {"metric": "Intention Conversion Rate", "value": f"{conversion_rate:.1%}",
     "definition": "Share of intentions that reach COMPLETED status"},
    {"metric": "Median Intention Survival Time", "value": f"{median_survival:.0f} days",
     "definition": "Median days from creation to terminal outcome (or last activity if still open)"},
    {"metric": "Research-to-Action Ratio (overall)", "value": f"{overall_rta_ratio:.2f}",
     "definition": "Total hours spent researching / total hours spent actually doing the thing"},
    {"metric": "Postponement Rate", "value": f"{postponement_rate:.1%}",
     "definition": "Share of intentions postponed at least once"},
    {"metric": "Zombie Intention Rate", "value": f"{zombie_rate:.1%}",
     "definition": "Share of intentions with real effort logged, then no activity for 120+ days, never formally closed"},
    {"metric": "Median Action Latency", "value": f"{median_action_latency:.0f} days",
     "definition": "Median days between creating an intention and actually starting it (among those that started)"},
    {"metric": "Median Completion Efficiency", "value": f"{median_completion_efficiency:.2f}x",
     "definition": "Actual hours spent / estimated hours, for completed intentions (>1 = took longer than estimated)"},
])
metrics_summary.to_csv(f"{OUT}/metrics_summary.csv", index=False)
print(metrics_summary.to_string(index=False))

# ---------------------------------------------------------------------------
# CHART 1: THE FUNNEL
# ---------------------------------------------------------------------------
funnel_stages = ["CREATED", "RESEARCHED", "PLANNED", "STARTED", "COMPLETED"]
funnel_counts = []
for stage in funnel_stages:
    if stage == "CREATED":
        funnel_counts.append(n_total)
    else:
        ids_reached = events.loc[events["event_type"] == stage, "intention_id"].nunique()
        funnel_counts.append(ids_reached)

plt.figure(figsize=(8, 5))
bars = plt.barh(funnel_stages[::-1], funnel_counts[::-1], color=sns.color_palette("Blues_r", len(funnel_stages)))
for bar, count in zip(bars, funnel_counts[::-1]):
    pct = count / n_total * 100
    plt.text(bar.get_width() + 4, bar.get_y() + bar.get_height() / 2,
              f"{count} ({pct:.0f}%)", va="center", fontsize=10)
plt.title("The Graveyard Funnel: Where Intentions Drop Off", fontsize=13)
plt.xlabel("Number of Intentions")
plt.xlim(0, n_total * 1.2)
plt.tight_layout()
plt.savefig(f"{OUT}/chart_01_funnel.png", dpi=150)
plt.close()

# ---------------------------------------------------------------------------
# CHART 2: FINAL STATUS BREAKDOWN (pie -> avoided; use a clean bar instead)
# ---------------------------------------------------------------------------
status_counts = master["status"].value_counts()
plt.figure(figsize=(7, 4.5))
order = ["COMPLETED", "ABANDONED", "REPLACED", "OPEN/STALLED"]
colors = {"COMPLETED": "#2E7D32", "ABANDONED": "#C62828", "REPLACED": "#F9A825", "OPEN/STALLED": "#616161"}
vals = [status_counts.get(s, 0) for s in order]
bars = plt.bar(order, vals, color=[colors[s] for s in order])
for bar, v in zip(bars, vals):
    plt.text(bar.get_x() + bar.get_width()/2, v + 3, f"{v}\n({v/n_total:.0%})", ha="center", fontsize=9)
plt.title("Final Status of All 320 Intentions")
plt.ylabel("Number of Intentions")
plt.tight_layout()
plt.savefig(f"{OUT}/chart_02_final_status.png", dpi=150)
plt.close()

# ---------------------------------------------------------------------------
# CHART 3: COMPLETION RATE BY CATEGORY
# ---------------------------------------------------------------------------
cat_completion = master.groupby("category_name")["status"].apply(
    lambda s: (s == "COMPLETED").mean()
).sort_values()

plt.figure(figsize=(8, 5.5))
plt.barh(cat_completion.index, cat_completion.values * 100, color="steelblue")
plt.title("Completion Rate by Category")
plt.xlabel("Completion Rate (%)")
plt.tight_layout()
plt.savefig(f"{OUT}/chart_03_completion_by_category.png", dpi=150)
plt.close()

# ---------------------------------------------------------------------------
# CHART 4: SURVIVAL TIME DISTRIBUTION BY OUTCOME
# ---------------------------------------------------------------------------
plt.figure(figsize=(8, 5))
sns.boxplot(
    data=master, x="status", y="survival_days",
    order=["COMPLETED", "ABANDONED", "REPLACED", "OPEN/STALLED"],
    hue="status", palette=colors, legend=False,
)
plt.title("Intention Survival Time by Final Status")
plt.ylabel("Days from creation to terminal event / last activity")
plt.xlabel("")
plt.tight_layout()
plt.savefig(f"{OUT}/chart_04_survival_by_status.png", dpi=150)
plt.close()

# ---------------------------------------------------------------------------
# CHART 5: DOES PERCEIVED IMPORTANCE PREDICT COMPLETION? (it barely does)
# ---------------------------------------------------------------------------
master["completed_flag"] = (master["status"] == "COMPLETED").astype(int)

fig, axes = plt.subplots(1, 3, figsize=(13, 4.2), sharey=True)
for ax, col, label in zip(
    axes,
    ["perceived_importance", "personal_interest", "urgency"],
    ["Perceived Importance", "Personal Interest", "Urgency"],
):
    rate_by_score = master.groupby(col)["completed_flag"].mean() * 100
    ax.bar(rate_by_score.index.astype(str), rate_by_score.values, color="teal")
    ax.set_title(label)
    ax.set_xlabel("Self-rated score (1-5)")
axes[0].set_ylabel("Completion Rate (%)")
plt.suptitle("Does Rating Something Important, Interesting, or Urgent Predict Completion?", fontsize=12)
plt.tight_layout()
plt.savefig(f"{OUT}/chart_05_predictors_of_completion.png", dpi=150)
plt.close()

# Quick correlation check (reported in text, not overinterpreted)
corr_importance, p_importance = stats.pointbiserialr(master["completed_flag"], master["perceived_importance"].fillna(master["perceived_importance"].median()))
corr_interest, p_interest = stats.pointbiserialr(master["completed_flag"], master["personal_interest"].fillna(master["personal_interest"].median()))
print(f"\nPoint-biserial correlation (completion vs. perceived_importance): r={corr_importance:.3f}, p={p_importance:.3f}")
print(f"Point-biserial correlation (completion vs. personal_interest):     r={corr_interest:.3f}, p={p_interest:.3f}")

# ---------------------------------------------------------------------------
# CHART 6: DEADLINE EFFECT ON OUTCOME MIX
# ---------------------------------------------------------------------------
deadline_ct = pd.crosstab(master["has_deadline"].astype(bool).map({True: "Has deadline", False: "No deadline"}), master["status"], normalize="index") * 100
deadline_ct = deadline_ct.reindex(columns=order, fill_value=0)

deadline_ct.plot(kind="bar", stacked=True, figsize=(7, 5), color=[colors[s] for s in order])
plt.title("Outcome Mix: Intentions With vs. Without a Deadline")
plt.ylabel("% of intentions in group")
plt.xlabel("")
plt.xticks(rotation=0)
plt.legend(title="Final status", bbox_to_anchor=(1.02, 1), loc="upper left")
plt.tight_layout()
plt.savefig(f"{OUT}/chart_06_deadline_effect.png", dpi=150)
plt.close()

# ---------------------------------------------------------------------------
# CHART 7: TOP BARRIERS FOR NON-COMPLETED INTENTIONS
# ---------------------------------------------------------------------------
barrier_merged = intention_barriers.merge(barriers_dim, on="barrier_id")
barrier_counts = barrier_merged["barrier_name"].value_counts().sort_values()

plt.figure(figsize=(8, 5.5))
plt.barh(barrier_counts.index, barrier_counts.values, color="indianred")
plt.title("Most Common Logged Barriers (Abandoned / Postponed Intentions)")
plt.xlabel("Number of intentions citing this barrier")
plt.tight_layout()
plt.savefig(f"{OUT}/chart_07_barriers.png", dpi=150)
plt.close()

# ---------------------------------------------------------------------------
# CHART 8: RESEARCH-TO-ACTION RATIO DISTRIBUTION
# ---------------------------------------------------------------------------
rta = master["research_to_action_ratio"].replace([np.inf, -np.inf], np.nan).dropna()
rta_capped = rta.clip(upper=rta.quantile(0.95))

plt.figure(figsize=(7.5, 4.5))
sns.histplot(rta_capped, bins=30, color="darkorange")
plt.axvline(1.0, color="black", linestyle="--", linewidth=1, label="Equal research & action time")
plt.title("Research-to-Action Ratio Across Intentions\n(capped at 95th percentile for readability)")
plt.xlabel("Research hours / Action hours")
plt.legend()
plt.tight_layout()
plt.savefig(f"{OUT}/chart_08_research_to_action.png", dpi=150)
plt.close()

# ---------------------------------------------------------------------------
# CHART 9: ZOMBIE INTENTIONS BY CATEGORY
# ---------------------------------------------------------------------------
zombie_by_cat = master.groupby("category_name")["is_zombie"].mean().sort_values() * 100
plt.figure(figsize=(8, 5.5))
plt.barh(zombie_by_cat.index, zombie_by_cat.values, color="slategray")
plt.title("Zombie Intention Rate by Category")
plt.xlabel("% of intentions in category that are 'zombies'")
plt.tight_layout()
plt.savefig(f"{OUT}/chart_09_zombie_by_category.png", dpi=150)
plt.close()

print("\nAll charts saved to outputs/. Master table saved to outputs/master_intention_table.csv")
print(f"\nTotal intentions: {n_total}")
print(f"Zombie intentions identified: {master['is_zombie'].sum()}")
