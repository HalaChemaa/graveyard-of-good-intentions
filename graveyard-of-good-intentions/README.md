# The Graveyard of Good Intentions
### An analysis of why intentions become actions — or disappear.

---

## Before the project: an honest self-critique

*(This section is here on purpose — a hiring manager who sees a project
anticipate its own weaknesses trusts the rest of it more.)*

**What's genuinely strong about this idea:** it's a real, relatable
analytical problem — not another Titanic/Iris rerun — with an actual
mechanism to investigate (a lifecycle with drop-off points), multiple
legitimate uses for SQL/Python/BI tools, and a dataset you can reason about
end-to-end because you designed it yourself.

**What could make it look amateurish, and how this build avoids it:**
- *A vague "productivity dashboard" with no real question.* → Fixed by
  having one specific, falsifiable question per analysis (e.g. "does
  perceived importance predict completion?" — answer: barely, r ≈ -0.06).
- *Synthetic data with suspiciously clean, engineered correlations.* → The
  generation logic (`scripts/01_generate_synthetic_data.py`) uses a noisy
  scoring function, not hard-coded outcomes, and the resulting correlations
  are weak and sometimes counter-intuitive — which is realistic and is
  disclosed openly in the Limitations section below, not hidden.
- *Every tool bolted on to check a box.* → Excel is the input layer only
  (not a rebuilt dashboard); SQL does the relational heavy lifting Python
  would do clumsily; Python does the stats/EDA; Power BI is the interactive
  operational view; Tableau is a fixed narrative Story — each tool has a
  distinct, defensible job (see `bi_specs/powerbi_tableau_specs.md`).
- *Sounding like a therapy diary instead of an analytics project.* → The
  framing throughout is operational (statuses, events, rates), never
  diagnostic. This is intentional and matters for how it reads to a
  reviewer.

**What a hiring manager needs to see to take it seriously:** a normalized
data model (not one flat spreadsheet), a visible data-cleaning step with a
real before/after, metrics with formulas and stated limitations, and a
finding that isn't just "most things don't get done" but has some texture
to it (e.g. deadlines barely moving the needle — see Finding 3 below).

**What was removed from the original scope:** a machine-learning model
predicting completion. With 320 intentions and weak underlying signal, an
ML model would be more likely to overfit and impress no one who checked the
work — a data analyst project doesn't need one, and honestly discussing
*why* it was left out is worth more than an unjustified model would be.

---

## 1. Executive Summary

This project tracks 320 synthetic "intentions" (goals, tasks, and projects
a person set out to do) across a ~2.5-year observation window, logging
every event in their lifecycle — researched, planned, started, worked on,
postponed, abandoned, replaced, or completed.

**Headline finding:** only **11.9%** of intentions were ever completed.
**63.4%** are neither finished nor formally abandoned — they simply went
quiet. Self-rated importance and urgency barely predict whether something
gets done; having a deadline barely moves the needle either. The strongest
(still modest) predictor is personal interest.

## 2. The Analytical Problem

People routinely intend to do far more than they complete — learn a skill,
apply for jobs, start exercising, build a project. The interesting question
isn't "did they finish," it's **where in the process things break down, and
whether the reasons people *say* something matters (important, urgent,
deadline-bound) actually predict whether they act on it.**

This matters because it's a pattern that shows up anywhere someone tracks
intent vs. follow-through — personal goal-setting, OKRs, backlog
grooming, sales pipelines. The lifecycle-with-drop-off-points structure
used here generalizes directly to those business contexts.

## 3. The Intention Lifecycle (Framework)

```
CREATED → RESEARCHED → PLANNED → STARTED → CONTINUED → COMPLETED
                ↓            ↓         ↓
           POSTPONED    ABANDONED   REPLACED
                                       ↓
                              (no further events = OPEN/STALLED)
```

Every intention is classified into exactly one **final status**, computed
from its event history:
- **COMPLETED** — a COMPLETED event exists
- **ABANDONED** — explicitly given up on
- **REPLACED** — explicitly dropped in favor of something else
- **OPEN/STALLED** — none of the above; simply stopped generating events

A separate derived flag, **`is_zombie`**, tags the subset of OPEN/STALLED
intentions where real effort was actually logged (research or work hours)
before it went quiet for 120+ consecutive days — distinguishing "genuinely
abandoned in spirit but never marked as such" from "created yesterday, too
early to judge."

## 4. Data Model

Normalized relational schema (SQLite, `db/graveyard.db`):

```
dim_category (category_id PK, category_name)
dim_barrier  (barrier_id PK, barrier_name)

intentions (
    intention_id PK, title, category_id FK, motivation, date_created,
    perceived_importance, urgency, personal_interest, career_relevance,
    estimated_effort_hours, has_deadline, deadline_date
)

intention_events (
    event_id PK, intention_id FK, event_date, event_type, hours_spent, note
)

intention_barriers (intention_id FK, barrier_id FK)        -- bridge table
intention_dependencies (intention_id FK, depends_on_intention_id FK)  -- self-referencing
```

**Why normalized rather than one flat table:** an intention has a *variable*
number of events (some have 15, some have 1), a *variable* number of
barriers, and can depend on other intentions. Flattening any of that into
one row per intention would mean either losing information or duplicating
the intention's static attributes across many rows — exactly the kind of
structure a relational database exists to handle, and exactly what makes
window functions and JOINs in the SQL file meaningful rather than
decorative.

Every stored field has a stated analytical purpose — no field was added
"because it sounded interesting":
| Field | Why it's there |
|---|---|
| `perceived_importance`, `urgency`, `personal_interest`, `career_relevance` | Test whether self-reported motivation predicts follow-through |
| `estimated_effort_hours` vs. logged `hours_spent` | Powers Completion Efficiency (were effort estimates realistic?) |
| `has_deadline` / `deadline_date` | Tests whether external structure changes outcomes |
| `event_type` sequence + `event_date` | The entire lifecycle/funnel/survival-time analysis depends on this |
| `note` / `dim_barrier` | Captures *why* something stalled, not just *that* it did |
| `intention_dependencies` | Tests whether chained/blocked intentions behave differently |

## 5. Data Pipeline

```
01_generate_synthetic_data.py   → clean "ground truth" (kept for reference only)
02_make_messy_raw_export.py     → data/raw/intention_log_raw_export.csv (deliberately messy)
03_clean_and_load.py            → cleans + normalizes → db/graveyard.db
04_python_analysis.py           → metrics + 9 charts → outputs/
05_build_excel_template.py      → excel/intention_tracker_template.xlsx (input layer)
```

The raw export mimics what a real hand-kept spreadsheet log would look
like: inconsistent category casing (`"Career"` / `"career "` / `"CAREER"`),
five different date formats, event types typed as free text (`"start"` /
`"Started"` / `"Began"`), Likert scores occasionally typed as words
("medium" instead of 3), a few negative-number typos, a few extreme
outlier entries, and 14 accidental duplicate rows.

**Cleaning report (from `data/clean/cleaning_report.txt`):**
| Issue | Count |
|---|---|
| Exact duplicate rows removed | 14 |
| Category / event-type text values unmapped (had to be dropped or flagged) | 0 |
| Negative `hours_spent` typos fixed (sign flipped) | 8 |
| Extreme `hours_spent` outliers capped at 60 hrs/session | 13 |
| Missing `perceived_importance` after cleaning | 5 |
| Missing `career_relevance` after cleaning | 12 |

1,432 raw rows → 1,418 clean event rows across 320 intentions.

## 6. Metrics

| Metric | Formula | Value | Why it matters | Limitation |
|---|---|---|---|---|
| **Intention Conversion Rate** | completed ÷ total | **11.9%** | The single headline number | Doesn't distinguish "abandoned early" from "died just short of the finish line" |
| **Median Intention Survival Time** | median(days: creation → terminal event / last activity) | **42 days** | How long an intention typically stays "alive" | Right-censored for still-open intentions — a true survival-analysis model (Kaplan-Meier) would handle this more rigorously |
| **Research-to-Action Ratio** | research hours ÷ action hours | **1.14** | Are people substituting research for actually doing the thing? | Only meaningful for intentions with nonzero action hours |
| **Postponement Rate** | % intentions postponed ≥1 time | **28.1%** | How often things get pushed back at least once | A single postponement isn't necessarily a bad sign — rate alone doesn't capture frequency per intention |
| **Zombie Intention Rate** | % with real effort logged, then 120+ days silent, never closed | **23.8%** | The "living dead" of the backlog — arguably the most actionable finding | The 120-day threshold is a judgment call, not a natural constant |
| **Action Latency** | median(days: creation → STARTED) | **59 days** | How long intentions sit before real work begins, among those that ever start | Only defined for intentions that reached STARTED (70 of 320) |
| **Completion Efficiency** | actual hours ÷ estimated hours (completed only) | **0.82×** | Were effort estimates realistic? | Small sample (38 completed intentions); no correction for estimate quality varying by category |

## 7. Key Findings

**Finding 1 — The graveyard is mostly silence, not rejection.**
63.4% of intentions end up OPEN/STALLED — never formally abandoned, just
quietly stopped. Only 20.6% are explicitly abandoned and 4.1% explicitly
replaced. This means most "failure" here isn't a decision, it's a lack of
one — which has a very different practical implication than active
rejection.

**Finding 2 — Stated importance and urgency are weak predictors; personal
interest is a slightly stronger (still weak) one.**
Point-biserial correlation with completion: perceived importance r ≈ -0.06
(p = 0.32, not significant), personal interest r ≈ 0.14 (p = 0.015,
significant but modest). People are not more likely to finish the things
they rate as important — they're a little more likely to finish the things
they find interesting.

**Finding 3 — Deadlines barely change the outcome mix.**
Intentions with a deadline completed at 12.4% vs. 11.7% without one — a
negligible difference given the sample. A deadline alone does not appear to
rescue an intention from stalling.

**Finding 4 — Category matters more than any individual trait.**
Completion rate ranges from 4.7% (Learning & Skills) to 19.4%
(Relationships) across categories — a wider spread than any of the 1-5
self-rated scores produced on their own, suggesting the *type* of intention
(and its natural friction/social accountability) matters more than how the
person rated it.

**Finding 5 — "Unclear next step" and "lack of motivation" are cited as
often as external barriers.**
Among logged barriers for stalled/abandoned intentions, "Lack of
motivation" and "Unclear next step" are the two most common (20 mentions
each), tied with or ahead of resource constraints like time and money —
suggesting friction in *how to proceed* is as big a blocker as competing
priorities.

## 8. Recommendations (framed for a hypothetical stakeholder — e.g. a
personal-productivity tool team, or a team backlog-health review)

1. **Build a "zombie" surfacing mechanism, not just a completion tracker.**
   The 76 zombie intentions identified here are invisible to a simple
   "done / not done" view — they need a distinct "stalled with sunk effort"
   state and a periodic nudge, since they're neither finished nor
   consciously dropped.
2. **Don't rely on self-rated importance/urgency as a triage signal.**
   Given how weakly they predicted completion here, a system that
   prioritizes purely by user-stated importance is prioritizing on a
   signal that barely correlates with what actually gets done.
3. **Address "unclear next step" directly.** Since this barrier is cited as
   often as resource constraints, prompting for a concrete next action at
   creation time (not just a vague goal) may reduce stalling more cheaply
   than addressing time/money constraints.
4. **Treat categories differently.** A one-size-fits-all nudge system
   ignores that some categories (e.g. Learning & Skills) may need
   structurally different support (accountability, cohorts) than others
   (e.g. Relationships) that complete at much higher rates on their own.

## 9. Limitations

- **The dataset is synthetic.** It is designed with plausible, noisy
  relationships rather than manufactured to produce clean findings, but it
  is not real behavioral data, and the specific numeric findings (11.9%
  conversion, etc.) should not be read as claims about real human behavior
  — they're a demonstration of the analytical approach.
- **The 120-day zombie threshold is a judgment call**, not derived from the
  data itself; a sensitivity analysis (60/90/120/180 days) would be a
  natural next step.
- **Survival time is right-censored** for still-open intentions; a proper
  survival analysis (Kaplan-Meier / Cox model) would handle this more
  rigorously than the simple "days to last activity" measure used here.
- **Correlational, not causal.** None of the findings in Section 7 support
  causal claims (e.g. "personal interest causes completion") — only
  association.
- **Barrier data is only ~75% complete** even for non-completed intentions
  (by design, mirroring how people don't always log why something stalled)
  — the barrier chart reflects what was logged, not necessarily the true
  full distribution of reasons.

## 10. Future Analysis

- Proper survival analysis (Kaplan-Meier curves by category) instead of
  median-days approximation.
- A sensitivity analysis on the zombie-intention threshold.
- If extended with real personal data: a within-person time-series view
  (does *this specific person's* conversion rate change over the 2.5 years,
  e.g. seasonally, or after a life change?).
- Text analysis on free-text `note` fields, if richer notes were collected,
  to surface barrier themes beyond the fixed `dim_barrier` list.

---

## 11. Interview Prep — Questions a Hiring Manager Might Ask

**1. "Why synthetic data, and how do I know it's not just showing me what
you wanted to find?"**
*Strong answer:* explain the noisy scoring function in
`01_generate_synthetic_data.py` — outcomes are probabilistic, not
hard-coded, and the resulting correlations are weak/mixed (including a
non-significant, slightly negative one for importance), which a
manufactured dataset would be unlikely to produce. Point to the Limitations
section as evidence of not overselling it.

**2. "Walk me through one thing you found in cleaning that surprised you or
changed your approach."**
*Strong answer:* the negative `hours_spent` typos and extreme outliers
needed an explicit business rule (cap at 60 hrs/session) rather than a
blind `.abs()` — shows judgment, not just mechanical cleaning.

**3. "Why a normalized schema instead of one flat CSV?"**
*Strong answer:* variable-length event histories per intention and a
many-to-many barrier relationship don't fit one row per intention without
either duplication or information loss — explain with a concrete example
(an intention with 6 events vs. one with 1).

**4. "Correlation vs. causation — are you claiming importance doesn't cause
completion?"**
*Strong answer:* no — only that self-*reported* importance doesn't strongly
*predict* completion in this data; there could be confounders (e.g. people
over-rate importance for things they already suspect they won't do), and
the design can't distinguish that from a true absence of effect.

**5. "Why no machine learning model to predict completion?"**
*Strong answer:* 320 rows and weak underlying signal is a recipe for an
overfit, unfalsifiable model; a descriptive/inferential approach (rates,
correlations, significance tests) answers the actual business question
more honestly at this sample size.

**6. "How did you decide on the 120-day zombie threshold?"**
*Strong answer:* acknowledge it's a judgment call, explain the reasoning
(long enough to rule out normal gaps between work sessions, short enough to
be actionable), and name the sensitivity analysis that should follow.

**7. "Why does Power BI get a dashboard and Tableau get a 'Story' instead
of the same dashboard twice?"**
*Strong answer:* they serve different purposes — Power BI for stakeholder
self-service exploration, Tableau Story for a fixed narrative a reader
consumes once — and doing the same thing twice would only demonstrate tool
syntax, not judgment about when each tool actually fits.

**8. "What would you do differently with more time or real data?"**
*Strong answer:* reference Section 10 — proper survival analysis, threshold
sensitivity testing, and (if using real personal data) a longitudinal
within-person view.

**9. "How do the SQL and Python analyses avoid just repeating each other?"**
*Strong answer:* SQL handles the relational aggregation (per-intention
rollups, window-function gap analysis, barrier joins) that would be
verbose in pandas; Python handles the statistical testing, visualization,
and the final derived master table that both the charts and BI exports are
built from — each is doing what it's actually better at.

**10. "What's the single most useful recommendation in here, and why?"**
*Strong answer:* the zombie-surfacing mechanism (Recommendation 1) — because
it's the only finding that identifies an *actionable, currently-invisible*
category (open-but-dead intentions), rather than just re-confirming that
importance/urgency/deadlines are weak signals, which is interesting but
less directly operational.

---

## Repository structure

```
data/raw/                    intention_log_raw_export.csv   (messy input)
data/clean/                  cleaned CSVs + cleaning_report.txt
db/graveyard.db              normalized SQLite database
scripts/                     01-05, the full pipeline, run in order
sql/analysis_queries.sql     11 annotated SQL queries (JOINs, CTEs, window fns, etc.)
outputs/                     9 charts, metrics_summary.csv, master_intention_table.csv
excel/                       intention_tracker_template.xlsx (input layer)
bi_specs/                    Power BI + Tableau design specification
```

## How to reproduce

```bash
pip install pandas numpy matplotlib seaborn scipy openpyxl
python scripts/01_generate_synthetic_data.py
python scripts/02_make_messy_raw_export.py
python scripts/03_clean_and_load.py
python scripts/04_python_analysis.py
python scripts/05_build_excel_template.py
```
