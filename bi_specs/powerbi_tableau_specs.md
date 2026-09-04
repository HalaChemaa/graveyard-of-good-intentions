# Power BI & Tableau Design Specs

This project deliberately does not duplicate the same dashboard in both
tools. **Power BI is the operational/exploratory dashboard** (filterable,
KPI-driven, built for a stakeholder to interrogate). **Tableau is a guided
Story** (a fixed narrative sequence, built to be read once, front to back,
like a short report).

Import `outputs/flat_table_for_bi.csv` (one row per intention — the main
model table) and `outputs/flat_events_for_bi.csv` (one row per event — for
anything time-series or funnel-shaped) into either tool.

---

## Part A — Power BI Dashboard (3 pages)

### Page 1: Overview — "Where do intentions actually end up?"
**Business question answered:** At a glance, what happens to the average
intention, and how big is the "graveyard"?

- **KPI cards (top row):** Total Intentions · Conversion Rate (% Completed)
  · Zombie Intention Rate · Median Survival Time (days)
- **Main visual:** Funnel chart — CREATED → RESEARCHED → PLANNED → STARTED →
  COMPLETED (matches `chart_01_funnel.png`)
- **Secondary visual:** Stacked bar — Final status breakdown (Completed /
  Abandoned / Replaced / Open-Stalled)
- **Filters (report-level slicers):** Category, Has Deadline, Date Created
  (range), Motivation
- **Key DAX measures:**
  ```
  Conversion Rate = DIVIDE(
      CALCULATE(COUNTROWS(Intentions), Intentions[status] = "COMPLETED"),
      COUNTROWS(Intentions)
  )

  Zombie Rate = DIVIDE(
      CALCULATE(COUNTROWS(Intentions), Intentions[is_zombie] = TRUE),
      COUNTROWS(Intentions)
  )

  Median Survival Days = MEDIAN(Intentions[survival_days])
  ```

### Page 2: Categories & Barriers — "Where does it break down, and why?"
**Business question answered:** Which categories of intention succeed or
stall, and what's actually blocking the ones that don't?

- **Visual 1:** Horizontal bar — Completion rate by category (matches
  `chart_03_completion_by_category.png`)
- **Visual 2:** Horizontal bar — Zombie rate by category
- **Visual 3:** Horizontal bar — Most common logged barriers (matches
  `chart_07_barriers.png`)
- **Interaction:** Clicking a category bar cross-filters the barriers chart
  — "for this category specifically, what's blocking it?"
- **Filters:** Same global slicers carried from Page 1 (Power BI syncs these
  automatically if slicers are set to apply across pages)

### Page 3: What Predicts Follow-Through? — "Does rating something important
actually make you more likely to do it?"
**Business question answered:** Do self-reported importance, interest, and
urgency actually predict completion — and does having a deadline help?

- **Visual 1:** Clustered bar — Completion rate by Perceived Importance /
  Personal Interest / Urgency score (matches `chart_05_predictors_of_completion.png`)
- **Visual 2:** 100%-stacked bar — Outcome mix, Has Deadline vs. No Deadline
  (matches `chart_06_deadline_effect.png`)
- **Visual 3:** Scatter — Estimated Effort Hours (x) vs. Survival Days (y),
  colored by final status
- **Key DAX measure:**
  ```
  Completion Rate by Score = DIVIDE(
      CALCULATE(COUNTROWS(Intentions), Intentions[status]="COMPLETED"),
      CALCULATE(COUNTROWS(Intentions))
  )
  -- placed on a bar chart with personal_interest (or importance/urgency) on the axis
  ```

**Deliberately excluded from Power BI:** a 4th page duplicating the SQL
barrier/dependency drill-down — that level of relational detail belongs in
the SQL queries file, not a dashboard page, to avoid a page that exists just
to "use the tool."

---

## Part B — Tableau Story: *"From Intention to Action: Where Do Good
Intentions Disappear?"*

A **Story** (not a dashboard) — 5 fixed points, each one Tableau sheet,
designed to be read in sequence like a short-form report rather than
explored freely.

| Story point | Sheet | Narrative beat |
|---|---|---|
| 1. The Funnel | Funnel chart (CREATED → COMPLETED) | "Out of 320 intentions, only 38 — 12% — were ever actually finished." |
| 2. It's Not About Not Caring | Grouped bar: completion rate by Importance / Interest / Urgency | "People don't abandon things they call unimportant. Self-rated importance barely predicts completion at all (r ≈ -0.06). Personal interest matters more (r ≈ 0.14) — but even that's a weak signal." |
| 3. Deadlines Don't Save You | 100%-stacked bar: outcome mix by deadline | "Intentions with a deadline complete at almost the same rate as those without one — deadlines don't rescue an intention that's lost momentum." |
| 4. The Graveyard Has a Shape | Horizontal bar: zombie rate by category + top barriers | "63% of intentions are neither finished nor formally given up on — they just go quiet. 'Unclear next step' and 'lack of motivation' are cited as often as anything external." |
| 5. So What Actually Helps? | Scatter: research hours vs. completion, annotated | "Closing takeaway + recommendations (see README §10)." |

**Tableau-specific techniques to use (for the "why Tableau and not just
another Power BI page" justification):**
- Story points with captions (Tableau's native Story feature) instead of
  static slide text
- A highlight action on Story Point 4 so hovering a category highlights its
  bar across both charts on that point
- Annotations directly on Story Point 5's scatter plot marking the "sweet
  spot" cluster (high research hours, low action hours = stuck in research)

---

## Field/measure reference (for building calculated fields in either tool)

| Field | Type | Source |
|---|---|---|
| `status` | Categorical | COMPLETED / ABANDONED / REPLACED / OPEN-STALLED |
| `is_zombie` | Boolean | True/False, computed in Python (see `04_python_analysis.py`) |
| `survival_days` | Numeric | Days from creation to terminal event / last activity |
| `research_to_action_ratio` | Numeric | research_hours / action_hours |
| `completion_efficiency` | Numeric | actual hours / estimated hours (completed only) |
| `action_latency_days` | Numeric | Days from creation to STARTED event |
