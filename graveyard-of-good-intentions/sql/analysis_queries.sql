-- ============================================================================
-- SQL ANALYSIS QUERIES — "The Graveyard of Good Intentions"
-- Database: db/graveyard.db (SQLite)
--
-- Each query answers a specific analytical question and is annotated with
-- why it matters and which SQL technique it demonstrates. Run with:
--   sqlite3 db/graveyard.db < sql/analysis_queries.sql
-- or load individually in any SQLite client / DB Browser for SQLite.
-- ============================================================================


-- ----------------------------------------------------------------------------
-- Q1. Overall funnel: how many intentions reach each lifecycle stage?
-- Technique: CASE + aggregate + subquery
-- Why it matters: this is the single most important chart in the whole
-- project — the "funnel" showing where intentions actually drop off.
-- ----------------------------------------------------------------------------
SELECT
    COUNT(*) AS total_intentions,
    SUM(CASE WHEN reached_researched THEN 1 ELSE 0 END) AS reached_researched,
    SUM(CASE WHEN reached_planned    THEN 1 ELSE 0 END) AS reached_planned,
    SUM(CASE WHEN reached_started    THEN 1 ELSE 0 END) AS reached_started,
    SUM(CASE WHEN reached_completed  THEN 1 ELSE 0 END) AS reached_completed
FROM (
    SELECT
        i.intention_id,
        MAX(CASE WHEN e.event_type = 'RESEARCHED' THEN 1 ELSE 0 END) AS reached_researched,
        MAX(CASE WHEN e.event_type = 'PLANNED'    THEN 1 ELSE 0 END) AS reached_planned,
        MAX(CASE WHEN e.event_type = 'STARTED'    THEN 1 ELSE 0 END) AS reached_started,
        MAX(CASE WHEN e.event_type = 'COMPLETED'  THEN 1 ELSE 0 END) AS reached_completed
    FROM intentions i
    LEFT JOIN intention_events e ON e.intention_id = i.intention_id
    GROUP BY i.intention_id
);


-- ----------------------------------------------------------------------------
-- Q2. Completion rate by category, ranked
-- Technique: JOIN + GROUP BY + CASE + ROUND
-- Why it matters: tells a stakeholder which categories of goal are most/least
-- likely to actually get done.
-- ----------------------------------------------------------------------------
SELECT
    c.category_name,
    COUNT(*) AS n_intentions,
    SUM(CASE WHEN outcome.final_status = 'COMPLETED' THEN 1 ELSE 0 END) AS n_completed,
    ROUND(100.0 * SUM(CASE WHEN outcome.final_status = 'COMPLETED' THEN 1 ELSE 0 END) / COUNT(*), 1) AS completion_rate_pct
FROM intentions i
JOIN dim_category c ON c.category_id = i.category_id
JOIN (
    -- one row per intention: its most recent terminal-ish status
    SELECT
        intention_id,
        CASE
            WHEN SUM(CASE WHEN event_type = 'COMPLETED' THEN 1 ELSE 0 END) > 0 THEN 'COMPLETED'
            WHEN SUM(CASE WHEN event_type = 'ABANDONED' THEN 1 ELSE 0 END) > 0 THEN 'ABANDONED'
            WHEN SUM(CASE WHEN event_type = 'REPLACED'  THEN 1 ELSE 0 END) > 0 THEN 'REPLACED'
            ELSE 'OPEN/STALLED'
        END AS final_status
    FROM intention_events
    GROUP BY intention_id
) outcome ON outcome.intention_id = i.intention_id
GROUP BY c.category_name
ORDER BY completion_rate_pct DESC;


-- ----------------------------------------------------------------------------
-- Q3. Final status classification for every intention (reusable CTE)
-- Technique: CTE (WITH clause) + CASE
-- Why it matters: this is the "single source of truth" for status, reused
-- across many later queries instead of repeating the same CASE logic.
-- ----------------------------------------------------------------------------
WITH final_status AS (
    SELECT
        intention_id,
        CASE
            WHEN SUM(CASE WHEN event_type = 'COMPLETED' THEN 1 ELSE 0 END) > 0 THEN 'COMPLETED'
            WHEN SUM(CASE WHEN event_type = 'ABANDONED' THEN 1 ELSE 0 END) > 0 THEN 'ABANDONED'
            WHEN SUM(CASE WHEN event_type = 'REPLACED'  THEN 1 ELSE 0 END) > 0 THEN 'REPLACED'
            ELSE 'OPEN/STALLED'
        END AS status
    FROM intention_events
    GROUP BY intention_id
)
SELECT status, COUNT(*) AS n, ROUND(100.0 * COUNT(*) / (SELECT COUNT(*) FROM intentions), 1) AS pct
FROM final_status
GROUP BY status
ORDER BY n DESC;


-- ----------------------------------------------------------------------------
-- Q4. Intention survival time: days from creation to terminal event
--     (or to the last logged event, for intentions that are still open)
-- Technique: JOIN + MIN/MAX date aggregation + julianday date arithmetic
-- Why it matters: powers the "Intention Survival Time" metric.
-- ----------------------------------------------------------------------------
SELECT
    i.intention_id,
    i.title,
    i.date_created,
    MAX(e.event_date) AS last_event_date,
    CAST(julianday(MAX(e.event_date)) - julianday(i.date_created) AS INTEGER) AS survival_days,
    CASE
        WHEN SUM(CASE WHEN e.event_type = 'COMPLETED' THEN 1 ELSE 0 END) > 0 THEN 'COMPLETED'
        WHEN SUM(CASE WHEN e.event_type = 'ABANDONED' THEN 1 ELSE 0 END) > 0 THEN 'ABANDONED'
        WHEN SUM(CASE WHEN e.event_type = 'REPLACED'  THEN 1 ELSE 0 END) > 0 THEN 'REPLACED'
        ELSE 'OPEN/STALLED'
    END AS final_status
FROM intentions i
JOIN intention_events e ON e.intention_id = i.intention_id
GROUP BY i.intention_id
ORDER BY survival_days DESC
LIMIT 20;


-- ----------------------------------------------------------------------------
-- Q5. Postponement count and "research-to-action ratio" per intention
-- Technique: multiple conditional aggregates in one pass + NULLIF to avoid
-- divide-by-zero
-- Why it matters: powers two metrics at once — Postponement Rate and
-- Research-to-Action Ratio (hours spent researching vs. hours spent doing).
-- ----------------------------------------------------------------------------
SELECT
    i.intention_id,
    i.title,
    SUM(CASE WHEN e.event_type = 'POSTPONED' THEN 1 ELSE 0 END) AS times_postponed,
    ROUND(SUM(CASE WHEN e.event_type = 'RESEARCHED' THEN e.hours_spent ELSE 0 END), 1) AS research_hours,
    ROUND(SUM(CASE WHEN e.event_type = 'CONTINUED'  THEN e.hours_spent ELSE 0 END), 1) AS action_hours,
    ROUND(
        SUM(CASE WHEN e.event_type = 'RESEARCHED' THEN e.hours_spent ELSE 0 END) * 1.0
        / NULLIF(SUM(CASE WHEN e.event_type = 'CONTINUED' THEN e.hours_spent ELSE 0 END), 0),
        2
    ) AS research_to_action_ratio
FROM intentions i
JOIN intention_events e ON e.intention_id = i.intention_id
GROUP BY i.intention_id
HAVING action_hours > 0 OR research_hours > 0
ORDER BY research_to_action_ratio DESC
LIMIT 20;


-- ----------------------------------------------------------------------------
-- Q6. Days between consecutive events per intention (gap analysis)
-- Technique: WINDOW FUNCTION (LAG) — flags the longest "silent gap" per
-- intention, a key ingredient of the Zombie Intention Rate.
-- ----------------------------------------------------------------------------
WITH ordered_events AS (
    SELECT
        intention_id,
        event_date,
        event_type,
        LAG(event_date) OVER (PARTITION BY intention_id ORDER BY event_date) AS prev_event_date
    FROM intention_events
),
gaps AS (
    SELECT
        intention_id,
        CAST(julianday(event_date) - julianday(prev_event_date) AS INTEGER) AS gap_days
    FROM ordered_events
    WHERE prev_event_date IS NOT NULL
)
SELECT
    intention_id,
    MAX(gap_days) AS longest_silent_gap_days
FROM gaps
GROUP BY intention_id
ORDER BY longest_silent_gap_days DESC
LIMIT 20;


-- ----------------------------------------------------------------------------
-- Q7. Zombie intentions: open/stalled AND no activity in the last 120 days
--     of the observation window (2025-08-01), AND at least one CONTINUED
--     or RESEARCHED event (i.e. real effort was put in, then it went cold)
-- Technique: CTE + window function (ROW_NUMBER/MAX) + date filter
-- Why it matters: powers the "Zombie Intention Rate" metric directly.
-- ----------------------------------------------------------------------------
WITH last_activity AS (
    SELECT
        intention_id,
        MAX(event_date) AS last_event_date,
        SUM(CASE WHEN event_type IN ('RESEARCHED','CONTINUED') THEN 1 ELSE 0 END) AS effort_events,
        SUM(CASE WHEN event_type IN ('COMPLETED','ABANDONED','REPLACED') THEN 1 ELSE 0 END) AS terminal_events
    FROM intention_events
    GROUP BY intention_id
)
SELECT
    i.intention_id,
    i.title,
    la.last_event_date,
    CAST(julianday('2025-08-01') - julianday(la.last_event_date) AS INTEGER) AS days_since_activity
FROM intentions i
JOIN last_activity la ON la.intention_id = i.intention_id
WHERE la.terminal_events = 0
  AND la.effort_events >= 1
  AND julianday('2025-08-01') - julianday(la.last_event_date) > 120
ORDER BY days_since_activity DESC;


-- ----------------------------------------------------------------------------
-- Q8. Does having a deadline change the outcome mix? (cross-tab style)
-- Technique: JOIN + CASE + GROUP BY on two dimensions
-- ----------------------------------------------------------------------------
WITH final_status AS (
    SELECT
        intention_id,
        CASE
            WHEN SUM(CASE WHEN event_type = 'COMPLETED' THEN 1 ELSE 0 END) > 0 THEN 'COMPLETED'
            WHEN SUM(CASE WHEN event_type = 'ABANDONED' THEN 1 ELSE 0 END) > 0 THEN 'ABANDONED'
            WHEN SUM(CASE WHEN event_type = 'REPLACED'  THEN 1 ELSE 0 END) > 0 THEN 'REPLACED'
            ELSE 'OPEN/STALLED'
        END AS status
    FROM intention_events
    GROUP BY intention_id
)
SELECT
    CASE WHEN i.has_deadline THEN 'Has deadline' ELSE 'No deadline' END AS deadline_group,
    fs.status,
    COUNT(*) AS n,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (PARTITION BY i.has_deadline), 1) AS pct_within_group
FROM intentions i
JOIN final_status fs ON fs.intention_id = i.intention_id
GROUP BY deadline_group, fs.status
ORDER BY deadline_group, n DESC;


-- ----------------------------------------------------------------------------
-- Q9. Most common barriers logged for abandoned/stalled intentions
-- Technique: JOIN across bridge table + GROUP BY + percentage window function
-- ----------------------------------------------------------------------------
SELECT
    b.barrier_name,
    COUNT(*) AS n_intentions,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 1) AS pct_of_logged_barriers
FROM intention_barriers ib
JOIN dim_barrier b ON b.barrier_id = ib.barrier_id
GROUP BY b.barrier_name
ORDER BY n_intentions DESC;


-- ----------------------------------------------------------------------------
-- Q10. Completion Efficiency: actual hours spent vs. estimated effort,
--      for completed intentions only
-- Technique: JOIN + aggregate + ratio, filtered subquery
-- Why it matters: powers the "Completion Efficiency" metric — were people
-- good at estimating how much work their intentions would take?
-- ----------------------------------------------------------------------------
WITH completed_ids AS (
    SELECT DISTINCT intention_id FROM intention_events WHERE event_type = 'COMPLETED'
),
actual_hours AS (
    SELECT intention_id, SUM(hours_spent) AS actual_hours
    FROM intention_events
    WHERE event_type IN ('RESEARCHED', 'CONTINUED')
    GROUP BY intention_id
)
SELECT
    i.intention_id,
    i.title,
    i.estimated_effort_hours,
    COALESCE(ah.actual_hours, 0) AS actual_hours,
    ROUND(COALESCE(ah.actual_hours, 0) / NULLIF(i.estimated_effort_hours, 0), 2) AS actual_to_estimated_ratio
FROM intentions i
JOIN completed_ids ci ON ci.intention_id = i.intention_id
LEFT JOIN actual_hours ah ON ah.intention_id = i.intention_id
ORDER BY actual_to_estimated_ratio DESC;


-- ----------------------------------------------------------------------------
-- Q11. Chained/dependent intentions still blocked by an unfinished prerequisite
-- Technique: self-referencing relationship + correlated subquery (NOT EXISTS)
-- ----------------------------------------------------------------------------
SELECT
    d.intention_id            AS blocked_intention,
    i1.title                  AS blocked_title,
    d.depends_on_intention_id AS waiting_on_intention,
    i2.title                  AS waiting_on_title
FROM intention_dependencies d
JOIN intentions i1 ON i1.intention_id = d.intention_id
JOIN intentions i2 ON i2.intention_id = d.depends_on_intention_id
WHERE NOT EXISTS (
    SELECT 1 FROM intention_events e
    WHERE e.intention_id = d.depends_on_intention_id
      AND e.event_type = 'COMPLETED'
);
