# Colleague Dashboard Parity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add waived tracking, % blocked KPIs, per-ecosystem breakdown, condition category/name pies, and exclude filter variables to both the Real Events and Dry Run Grafana dashboards.

**Architecture:** All changes are confined to `scripts/generate_dashboards.py` (the dashboard generator) plus two builder helper updates (`_stat`, `_timeseries`, `_pie`). After each logical addition the script is regenerated and the output JSON is spot-checked. No ETL, schema, or Docker changes are needed — `action='waived'` is already stored as-is by the ETL.

**Tech Stack:** Python 3, Grafana provisioned JSON dashboards, PostgreSQL 16.

---

## File Map

| File | What changes |
|---|---|
| `scripts/generate_dashboards.py` | All changes live here |
| `grafana/provisioning/dashboards/real-events.json` | Regenerated output — do not edit by hand |
| `grafana/provisioning/dashboards/dry-run.json` | Regenerated output — do not edit by hand |

---

## Task 1: Extend `_stat()`, `_timeseries()`, and `_pie()` builders; add `_barchart()`

The three existing builders have hardcoded widths or fixed series counts that need to flex for the new panels.

**Files:**
- Modify: `scripts/generate_dashboards.py:15-85` (builder functions)

- [ ] **Step 1: Verify current panel counts before any changes**

```bash
python3 -c "
import json
for f in ['grafana/provisioning/dashboards/real-events.json',
          'grafana/provisioning/dashboards/dry-run.json']:
    d = json.load(open(f))
    print(f, '->', len(d['panels']), 'panels')
"
```
Expected output:
```
grafana/provisioning/dashboards/real-events.json -> 12 panels
grafana/provisioning/dashboards/dry-run.json -> 9 panels
```

- [ ] **Step 2: Update `_stat()` to accept an optional `grid_w` parameter**

Replace the existing `_stat` function (lines 15-31):

```python
def _stat(title, sql, color, grid_x, grid_y, grid_w=6):
    return {
        "type": "stat",
        "title": title,
        "datasource": DS_REF,
        "gridPos": {"h": 4, "w": grid_w, "x": grid_x, "y": grid_y},
        "options": {
            "reduceOptions": {"calcs": ["lastNotNull"]},
            "colorMode": "value",
            "graphMode": "none",
        },
        "fieldConfig": {
            "defaults": {"color": {"fixedColor": color, "mode": "fixed"}},
            "overrides": [],
        },
        "targets": [{"datasource": DS_REF, "rawSql": sql, "format": "table", "refId": "A"}],
    }
```

- [ ] **Step 3: Update `_timeseries()` to accept an optional `sql_waived` parameter**

Replace the existing `_timeseries` function (lines 34-61):

```python
def _timeseries(title, sql_approved, sql_blocked, grid_y, sql_waived=None):
    overrides = [
        {
            "matcher": {"id": "byName", "options": "approved"},
            "properties": [{"id": "color", "value": {"fixedColor": "green", "mode": "fixed"}}],
        },
        {
            "matcher": {"id": "byName", "options": "blocked"},
            "properties": [{"id": "color", "value": {"fixedColor": "red", "mode": "fixed"}}],
        },
    ]
    if sql_waived:
        overrides.append({
            "matcher": {"id": "byName", "options": "waived"},
            "properties": [{"id": "color", "value": {"fixedColor": "#d29922", "mode": "fixed"}}],
        })
    targets = [
        {"datasource": DS_REF, "rawSql": sql_approved, "format": "time_series", "refId": "A"},
        {"datasource": DS_REF, "rawSql": sql_blocked,  "format": "time_series", "refId": "B"},
    ]
    if sql_waived:
        targets.append({"datasource": DS_REF, "rawSql": sql_waived, "format": "time_series", "refId": "C"})
    return {
        "type": "timeseries",
        "title": title,
        "datasource": DS_REF,
        "gridPos": {"h": 8, "w": 24, "x": 0, "y": grid_y},
        "options": {
            "tooltip": {"mode": "multi"},
            "legend": {"displayMode": "list", "placement": "bottom"},
        },
        "fieldConfig": {
            "defaults": {"custom": {"lineWidth": 2, "fillOpacity": 10}},
            "overrides": overrides,
        },
        "targets": targets,
    }
```

- [ ] **Step 4: Update `_pie()` to accept an optional `grid_w` parameter**

Replace the existing `_pie` function (lines 76-85):

```python
def _pie(title, sql, grid_y, grid_x=12, grid_w=12):
    return {
        "type": "piechart",
        "title": title,
        "datasource": DS_REF,
        "gridPos": {"h": 8, "w": grid_w, "x": grid_x, "y": grid_y},
        "options": {"pieType": "pie", "legend": {"displayMode": "table", "placement": "right"}},
        "fieldConfig": {"defaults": {}, "overrides": []},
        "targets": [{"datasource": DS_REF, "rawSql": sql, "format": "table", "refId": "A"}],
    }
```

- [ ] **Step 5: Add `_barchart()` builder after `_pie()`**

Insert after the `_pie` function and before `_var`:

```python
def _barchart(title, sql, grid_y, grid_x=0, grid_w=12, orientation="auto"):
    return {
        "type": "barchart",
        "title": title,
        "datasource": DS_REF,
        "gridPos": {"h": 8, "w": grid_w, "x": grid_x, "y": grid_y},
        "options": {
            "orientation": orientation,
            "legend": {"displayMode": "list", "placement": "bottom"},
            "tooltip": {"mode": "multi"},
        },
        "fieldConfig": {"defaults": {}, "overrides": []},
        "targets": [{"datasource": DS_REF, "rawSql": sql, "format": "table", "refId": "A"}],
    }
```

- [ ] **Step 6: Run the generator to confirm no syntax errors**

```bash
python3 scripts/generate_dashboards.py
```
Expected:
```
Written: grafana/provisioning/dashboards/real-events.json
Written: grafana/provisioning/dashboards/dry-run.json
```
Panel counts must still be 12 and 9 (no panels added yet — builders only).

- [ ] **Step 7: Commit**

```bash
git add scripts/generate_dashboards.py grafana/provisioning/dashboards/
git commit -m "feat: extend stat/timeseries/pie builders; add _barchart builder"
```

---

## Task 2: Rebuild `real_events()` — stats row, timeseries, ecosystem row

**Files:**
- Modify: `scripts/generate_dashboards.py` — `real_events()` function

- [ ] **Step 1: Replace the `real_events()` panel list and variables**

Replace the entire `real_events()` function body (from `def real_events():` to its `return` statement) with the following. Read carefully — every panel position is deliberate.

```python
def real_events():
    w          = _where("false")
    w_blocked  = _where("false", extra_filters="AND action = 'blocked'")
    w_approved = _where("false", extra_filters="AND action = 'approved'")
    w_waived   = _where("false", extra_filters="AND action = 'waived'")
    wj = (
        "WHERE ae.is_dry_run = false"
        " AND $__timeFilter(ae.created_at)"
        " AND ('$package_type' = ANY(ARRAY['', 'All']) OR ae.package_type = '$package_type')"
        " AND ('$repository' = ANY(ARRAY['', 'All']) OR ae.curated_repository_name = '$repository')"
    )

    panels = [
        # ── Stats row (6 × w=4) ────────────────────────────────────────────
        _stat("Total Events",
              f"SELECT COUNT(*) FROM audit_events {w}",
              "blue",   0,  0, grid_w=4),
        _stat("% Blocked",
              f"SELECT ROUND(100.0 * SUM(CASE WHEN action = 'blocked' THEN 1 ELSE 0 END)"
              f" / NULLIF(COUNT(*), 0), 1) AS pct_blocked FROM audit_events {w}",
              "orange", 4,  0, grid_w=4),
        _stat("Blocked",
              f"SELECT COUNT(*) FROM audit_events {w_blocked}",
              "red",    8,  0, grid_w=4),
        _stat("Approved",
              f"SELECT COUNT(*) FROM audit_events {w_approved}",
              "green",  12, 0, grid_w=4),
        _stat("Waived",
              f"SELECT COUNT(*) FROM audit_events {w_waived}",
              "#d29922", 16, 0, grid_w=4),
        _stat("Unique Packages",
              f"SELECT COUNT(DISTINCT package_name) FROM audit_events {w}",
              "purple", 20, 0, grid_w=4),

        # ── Timeseries with waived ─────────────────────────────────────────
        _timeseries(
            "Blocked / Approved / Waived Over Time",
            _trend_sql("false", "approved"),
            _trend_sql("false", "blocked"),
            grid_y=4,
            sql_waived=_trend_sql("false", "waived"),
        ),

        # ── Ecosystem breakdown row (y=12) ─────────────────────────────────
        _barchart(
            "Approved / Blocked / Waived by Ecosystem",
            f"""SELECT
  package_type,
  SUM(CASE WHEN action = 'approved' THEN 1 ELSE 0 END) AS approved,
  SUM(CASE WHEN action = 'blocked'  THEN 1 ELSE 0 END) AS blocked,
  SUM(CASE WHEN action = 'waived'   THEN 1 ELSE 0 END) AS waived
FROM audit_events
{w}
GROUP BY package_type
ORDER BY (SUM(CASE WHEN action = 'approved' THEN 1 ELSE 0 END)
        + SUM(CASE WHEN action = 'blocked'  THEN 1 ELSE 0 END)
        + SUM(CASE WHEN action = 'waived'   THEN 1 ELSE 0 END)) DESC""",
            grid_y=12, grid_x=0, grid_w=12,
        ),
        _barchart(
            "% Blocked by Ecosystem",
            f"""SELECT
  package_type,
  ROUND(100.0 * SUM(CASE WHEN action = 'blocked' THEN 1 ELSE 0 END)
        / NULLIF(COUNT(*), 0), 1) AS pct_blocked
FROM audit_events
{w}
GROUP BY package_type
ORDER BY pct_blocked DESC""",
            grid_y=12, grid_x=12, grid_w=12, orientation="horizontal",
        ),

        # ── Condition analysis row (y=20) ──────────────────────────────────
        _table(
            "Top Blocked Packages",
            f"""SELECT
  package_name,
  package_type,
  COUNT(*) AS blocked_count,
  MAX(reason) AS last_reason
FROM audit_events
{w_blocked}
GROUP BY package_name, package_type
ORDER BY blocked_count DESC
LIMIT 20""",
            grid_y=20, grid_x=0, grid_w=8,
        ),
        _pie(
            "Blocked by Condition Category",
            f"""SELECT
  COALESCE(ep.condition_category, 'N/A') AS condition_category,
  COUNT(*) AS count
FROM audit_events ae
JOIN event_policies ep ON ae.id = ep.event_id
{wj}
  AND ae.action = 'blocked'
  AND (ep.condition_category != '$exclude_condition_category'
       OR '$exclude_condition_category' = '')
GROUP BY ep.condition_category
ORDER BY count DESC""",
            grid_y=20, grid_x=8, grid_w=8,
        ),
        _pie(
            "Blocked by Condition Name",
            f"""SELECT
  COALESCE(ep.condition_name, 'N/A') AS condition_name,
  COUNT(*) AS count
FROM audit_events ae
JOIN event_policies ep ON ae.id = ep.event_id
{wj}
  AND ae.action = 'blocked'
  AND (ep.condition_name != '$exclude_condition_name'
       OR '$exclude_condition_name' = '')
GROUP BY ep.condition_name
ORDER BY count DESC""",
            grid_y=20, grid_x=16, grid_w=8,
        ),

        # ── Policy / waived / user-activity row (y=28) ────────────────────
        _table(
            "Policy Breakdown",
            f"""SELECT
  ep.policy_name,
  COUNT(*) AS triggered_count
FROM audit_events ae
JOIN event_policies ep ON ae.id = ep.event_id
{wj}
GROUP BY ep.policy_name
ORDER BY triggered_count DESC""",
            grid_y=28, grid_x=0, grid_w=8,
        ),
        _pie(
            "Waived by Ecosystem",
            f"""SELECT
  package_type,
  COUNT(*) AS count
FROM audit_events
{w_waived}
GROUP BY package_type
ORDER BY count DESC""",
            grid_y=28, grid_x=8, grid_w=8,
        ),
        _table(
            "User Activity",
            f"""SELECT
  username,
  COUNT(*) AS total_events,
  SUM(CASE WHEN action = 'blocked'  THEN 1 ELSE 0 END) AS blocked_count,
  SUM(CASE WHEN action = 'approved' THEN 1 ELSE 0 END) AS approved_count,
  SUM(CASE WHEN action = 'waived'   THEN 1 ELSE 0 END) AS waived_count
FROM audit_events
{w}
GROUP BY username
ORDER BY total_events DESC
LIMIT 20""",
            grid_y=28, grid_x=16, grid_w=8,
        ),

        # ── 12-hour window analysis (existing, pushed to y=36/44) ──────────
        _stat(
            "High-Persistence Users",
            """SELECT COUNT(DISTINCT username)
FROM (
  SELECT username,
    SUM(is_window_start) AS sessions
  FROM mv_download_windows
  WHERE is_dry_run = false AND action = 'blocked'
    AND $__timeFilter(created_at)
    AND ('$package_type' = ANY(ARRAY['', 'All']) OR package_type = '$package_type')
    AND ('$repository' = ANY(ARRAY['', 'All']) OR curated_repository_name = '$repository')
  GROUP BY username, package_name
  HAVING SUM(is_window_start) >= 3
) sub""",
            "orange", 0, 36,
        ),
        _table(
            "Persistent Blocked Packages",
            """SELECT
  package_name,
  package_type,
  username,
  SUM(is_window_start) AS unique_sessions,
  COUNT(*) AS total_events,
  MIN(created_at) AS first_seen,
  MAX(created_at) AS last_seen
FROM mv_download_windows
WHERE is_dry_run = false AND action = 'blocked'
  AND $__timeFilter(created_at)
  AND ('$package_type' = ANY(ARRAY['', 'All']) OR package_type = '$package_type')
  AND ('$repository' = ANY(ARRAY['', 'All']) OR curated_repository_name = '$repository')
GROUP BY package_name, package_type, username
HAVING SUM(is_window_start) > 1
ORDER BY unique_sessions DESC
LIMIT 20""",
            grid_y=36, grid_x=6, grid_w=18,
        ),
        _timeseries(
            "Download Sessions Over Time",
            """SELECT
  $__timeGroupAlias(created_at,'1d'),
  COUNT(*) AS approved
FROM mv_download_windows
WHERE is_dry_run = false AND action = 'approved'
  AND is_window_start = 1
  AND $__timeFilter(created_at)
  AND ('$package_type' = ANY(ARRAY['', 'All']) OR package_type = '$package_type')
  AND ('$repository' = ANY(ARRAY['', 'All']) OR curated_repository_name = '$repository')
GROUP BY 1
ORDER BY 1""",
            """SELECT
  $__timeGroupAlias(created_at,'1d'),
  COUNT(*) AS blocked
FROM mv_download_windows
WHERE is_dry_run = false AND action = 'blocked'
  AND is_window_start = 1
  AND $__timeFilter(created_at)
  AND ('$package_type' = ANY(ARRAY['', 'All']) OR package_type = '$package_type')
  AND ('$repository' = ANY(ARRAY['', 'All']) OR curated_repository_name = '$repository')
GROUP BY 1
ORDER BY 1""",
            grid_y=44,
        ),
    ]

    variables = [
        _var(
            "package_type", "Package Type",
            "SELECT 'All' AS package_type UNION SELECT DISTINCT package_type"
            " FROM audit_events WHERE is_dry_run = false ORDER BY 1",
        ),
        _var(
            "repository", "Repository",
            "SELECT 'All' AS curated_repository_name UNION SELECT DISTINCT curated_repository_name"
            " FROM audit_events WHERE is_dry_run = false ORDER BY 1",
        ),
        _var(
            "exclude_condition_category", "Exclude Condition Category",
            "SELECT '' AS condition_category UNION SELECT DISTINCT condition_category"
            " FROM event_policies WHERE condition_category IS NOT NULL ORDER BY 1",
        ),
        _var(
            "exclude_condition_name", "Exclude Condition Name",
            "SELECT '' AS condition_name UNION SELECT DISTINCT condition_name"
            " FROM event_policies WHERE condition_name IS NOT NULL ORDER BY 1",
        ),
    ]

    return _dashboard("Curation Audit \u2014 Real Events", "curation-real-events", panels, variables)
```

- [ ] **Step 2: Run the generator and verify panel count**

```bash
python3 scripts/generate_dashboards.py
```
Expected output: both files written without error.

```bash
python3 -c "
import json
d = json.load(open('grafana/provisioning/dashboards/real-events.json'))
print('panels:', len(d['panels']))
print('variables:', [v['name'] for v in d['templating']['list']])
titles = [p['title'] for p in d['panels']]
for t in titles: print(' ', t)
"
```
Expected:
```
panels: 18
variables: ['package_type', 'repository', 'exclude_condition_category', 'exclude_condition_name']
  Total Events
  % Blocked
  Blocked
  Approved
  Waived
  Unique Packages
  Blocked / Approved / Waived Over Time
  Approved / Blocked / Waived by Ecosystem
  % Blocked by Ecosystem
  Top Blocked Packages
  Blocked by Condition Category
  Blocked by Condition Name
  Policy Breakdown
  Waived by Ecosystem
  User Activity
  High-Persistence Users
  Persistent Blocked Packages
  Download Sessions Over Time
```

- [ ] **Step 3: Commit**

```bash
git add scripts/generate_dashboards.py grafana/provisioning/dashboards/real-events.json
git commit -m "feat: rebuild real events dashboard with waived, ecosystem breakdown, condition pies"
```

---

## Task 3: Rebuild `dry_run()` — mirror all additions

**Files:**
- Modify: `scripts/generate_dashboards.py` — `dry_run()` function

- [ ] **Step 1: Replace the entire `dry_run()` function body**

```python
def dry_run():
    w          = _where("true", include_repo_filter=False)
    w_blocked  = _where("true", extra_filters="AND action = 'blocked'", include_repo_filter=False)
    w_approved = _where("true", extra_filters="AND action = 'approved'", include_repo_filter=False)
    w_waived   = _where("true", extra_filters="AND action = 'waived'",  include_repo_filter=False)
    wj = (
        "WHERE ae.is_dry_run = true"
        " AND $__timeFilter(ae.created_at)"
        " AND ('$package_type' = ANY(ARRAY['', 'All']) OR ae.package_type = '$package_type')"
    )

    panels = [
        # ── Stats row (6 × w=4) ────────────────────────────────────────────
        _stat("Total Dry-Run Events",
              f"SELECT COUNT(*) FROM audit_events {w}",
              "blue",    0,  0, grid_w=4),
        _stat("% Would Be Blocked",
              f"SELECT ROUND(100.0 * SUM(CASE WHEN action = 'blocked' THEN 1 ELSE 0 END)"
              f" / NULLIF(COUNT(*), 0), 1) AS pct_blocked FROM audit_events {w}",
              "orange",  4,  0, grid_w=4),
        _stat("Would Be Blocked",
              f"SELECT COUNT(*) FROM audit_events {w_blocked}",
              "red",     8,  0, grid_w=4),
        _stat("Would Be Approved",
              f"SELECT COUNT(*) FROM audit_events {w_approved}",
              "green",   12, 0, grid_w=4),
        _stat("Would Be Waived",
              f"SELECT COUNT(*) FROM audit_events {w_waived}",
              "#d29922", 16, 0, grid_w=4),
        _stat("Unique Packages",
              f"SELECT COUNT(DISTINCT package_name) FROM audit_events {w}",
              "purple",  20, 0, grid_w=4),

        # ── Timeseries with waived ─────────────────────────────────────────
        _timeseries(
            "Simulated Blocked / Approved / Waived Over Time",
            _trend_sql("true", "approved", include_repo_filter=False),
            _trend_sql("true", "blocked",  include_repo_filter=False),
            grid_y=4,
            sql_waived=_trend_sql("true", "waived", include_repo_filter=False),
        ),

        # ── Ecosystem breakdown row (y=12) ─────────────────────────────────
        _barchart(
            "Approved / Blocked / Waived by Ecosystem",
            f"""SELECT
  package_type,
  SUM(CASE WHEN action = 'approved' THEN 1 ELSE 0 END) AS approved,
  SUM(CASE WHEN action = 'blocked'  THEN 1 ELSE 0 END) AS blocked,
  SUM(CASE WHEN action = 'waived'   THEN 1 ELSE 0 END) AS waived
FROM audit_events
{w}
GROUP BY package_type
ORDER BY (SUM(CASE WHEN action = 'approved' THEN 1 ELSE 0 END)
        + SUM(CASE WHEN action = 'blocked'  THEN 1 ELSE 0 END)
        + SUM(CASE WHEN action = 'waived'   THEN 1 ELSE 0 END)) DESC""",
            grid_y=12, grid_x=0, grid_w=12,
        ),
        _barchart(
            "% Would Be Blocked by Ecosystem",
            f"""SELECT
  package_type,
  ROUND(100.0 * SUM(CASE WHEN action = 'blocked' THEN 1 ELSE 0 END)
        / NULLIF(COUNT(*), 0), 1) AS pct_blocked
FROM audit_events
{w}
GROUP BY package_type
ORDER BY pct_blocked DESC""",
            grid_y=12, grid_x=12, grid_w=12, orientation="horizontal",
        ),

        # ── Condition analysis row (y=20) ──────────────────────────────────
        _table(
            "Top Would-Be Blocked Packages",
            f"""SELECT
  package_name,
  package_type,
  COUNT(*) AS block_count
FROM audit_events
{w_blocked}
GROUP BY package_name, package_type
ORDER BY block_count DESC
LIMIT 20""",
            grid_y=20, grid_x=0, grid_w=8,
        ),
        _pie(
            "Would-Be Blocked by Condition Category",
            f"""SELECT
  COALESCE(ep.condition_category, 'N/A') AS condition_category,
  COUNT(*) AS count
FROM audit_events ae
JOIN event_policies ep ON ae.id = ep.event_id
{wj}
  AND ae.action = 'blocked'
  AND (ep.condition_category != '$exclude_condition_category'
       OR '$exclude_condition_category' = '')
GROUP BY ep.condition_category
ORDER BY count DESC""",
            grid_y=20, grid_x=8, grid_w=8,
        ),
        _pie(
            "Would-Be Blocked by Condition Name",
            f"""SELECT
  COALESCE(ep.condition_name, 'N/A') AS condition_name,
  COUNT(*) AS count
FROM audit_events ae
JOIN event_policies ep ON ae.id = ep.event_id
{wj}
  AND ae.action = 'blocked'
  AND (ep.condition_name != '$exclude_condition_name'
       OR '$exclude_condition_name' = '')
GROUP BY ep.condition_name
ORDER BY count DESC""",
            grid_y=20, grid_x=16, grid_w=8,
        ),

        # ── Policy / waived / user-activity row (y=28) ────────────────────
        _table(
            "Dry-Run Policy Breakdown",
            f"""SELECT
  ep.policy_name,
  COUNT(*) AS triggered_count
FROM audit_events ae
JOIN event_policies ep ON ae.id = ep.event_id
{wj}
GROUP BY ep.policy_name
ORDER BY triggered_count DESC""",
            grid_y=28, grid_x=0, grid_w=8,
        ),
        _pie(
            "Would-Be Waived by Ecosystem",
            f"""SELECT
  package_type,
  COUNT(*) AS count
FROM audit_events
{w_waived}
GROUP BY package_type
ORDER BY count DESC""",
            grid_y=28, grid_x=8, grid_w=8,
        ),
        _table(
            "User Activity",
            f"""SELECT
  username,
  COUNT(*) AS total_events,
  SUM(CASE WHEN action = 'blocked'  THEN 1 ELSE 0 END) AS blocked_count,
  SUM(CASE WHEN action = 'approved' THEN 1 ELSE 0 END) AS approved_count,
  SUM(CASE WHEN action = 'waived'   THEN 1 ELSE 0 END) AS waived_count
FROM audit_events
{w}
GROUP BY username
ORDER BY total_events DESC
LIMIT 20""",
            grid_y=28, grid_x=16, grid_w=8,
        ),

        # ── 12-hour window analysis (existing, pushed to y=36/44) ──────────
        _stat(
            "High-Persistence Users",
            """SELECT COUNT(DISTINCT username)
FROM (
  SELECT username,
    SUM(is_window_start) AS sessions
  FROM mv_download_windows
  WHERE is_dry_run = true AND action = 'blocked'
    AND $__timeFilter(created_at)
    AND ('$package_type' = ANY(ARRAY['', 'All']) OR package_type = '$package_type')
  GROUP BY username, package_name
  HAVING SUM(is_window_start) >= 3
) sub""",
            "orange", 0, 36,
        ),
        _table(
            "Persistent Blocked Packages",
            """SELECT
  package_name,
  package_type,
  username,
  SUM(is_window_start) AS unique_sessions,
  COUNT(*) AS total_events,
  MIN(created_at) AS first_seen,
  MAX(created_at) AS last_seen
FROM mv_download_windows
WHERE is_dry_run = true AND action = 'blocked'
  AND $__timeFilter(created_at)
  AND ('$package_type' = ANY(ARRAY['', 'All']) OR package_type = '$package_type')
GROUP BY package_name, package_type, username
HAVING SUM(is_window_start) > 1
ORDER BY unique_sessions DESC
LIMIT 20""",
            grid_y=36, grid_x=6, grid_w=18,
        ),
        _timeseries(
            "Download Sessions Over Time",
            """SELECT
  $__timeGroupAlias(created_at,'1d'),
  COUNT(*) AS approved
FROM mv_download_windows
WHERE is_dry_run = true AND action = 'approved'
  AND is_window_start = 1
  AND $__timeFilter(created_at)
  AND ('$package_type' = ANY(ARRAY['', 'All']) OR package_type = '$package_type')
GROUP BY 1
ORDER BY 1""",
            """SELECT
  $__timeGroupAlias(created_at,'1d'),
  COUNT(*) AS blocked
FROM mv_download_windows
WHERE is_dry_run = true AND action = 'blocked'
  AND is_window_start = 1
  AND $__timeFilter(created_at)
  AND ('$package_type' = ANY(ARRAY['', 'All']) OR package_type = '$package_type')
GROUP BY 1
ORDER BY 1""",
            grid_y=44,
        ),
    ]

    variables = [
        _var(
            "package_type", "Package Type",
            "SELECT 'All' AS package_type UNION SELECT DISTINCT package_type"
            " FROM audit_events WHERE is_dry_run = true ORDER BY 1",
        ),
        _var(
            "exclude_condition_category", "Exclude Condition Category",
            "SELECT '' AS condition_category UNION SELECT DISTINCT condition_category"
            " FROM event_policies WHERE condition_category IS NOT NULL ORDER BY 1",
        ),
        _var(
            "exclude_condition_name", "Exclude Condition Name",
            "SELECT '' AS condition_name UNION SELECT DISTINCT condition_name"
            " FROM event_policies WHERE condition_name IS NOT NULL ORDER BY 1",
        ),
    ]

    return _dashboard("Curation Audit \u2014 Dry Run", "curation-dry-run", panels, variables)
```

- [ ] **Step 2: Run the generator and verify dry-run panel count**

```bash
python3 scripts/generate_dashboards.py
python3 -c "
import json
d = json.load(open('grafana/provisioning/dashboards/dry-run.json'))
print('panels:', len(d['panels']))
print('variables:', [v['name'] for v in d['templating']['list']])
"
```
Expected:
```
panels: 18
variables: ['package_type', 'exclude_condition_category', 'exclude_condition_name']
```

- [ ] **Step 3: Commit**

```bash
git add scripts/generate_dashboards.py grafana/provisioning/dashboards/dry-run.json
git commit -m "feat: rebuild dry run dashboard to match real events parity"
```

---

## Task 4: End-to-end verification

**Files:** No edits — read-only verification.

- [ ] **Step 1: Start the stack**

```bash
docker compose up -d postgres grafana
```
Wait ~15 seconds for Grafana to load provisioned dashboards.

- [ ] **Step 2: Confirm both dashboards load in Grafana**

Open `http://localhost:3000` (login: admin / admin).
Navigate to Dashboards → Curation Audit folder.

Check Real Events dashboard:
- Stats row: 6 panels visible (Total Events · % Blocked · Blocked · Approved · Waived · Unique Packages)
- "Blocked / Approved / Waived Over Time" timeseries visible
- "Approved / Blocked / Waived by Ecosystem" bar chart visible (may show empty data — that's fine)
- "% Blocked by Ecosystem" horizontal bar chart visible
- "Blocked by Condition Category" and "Blocked by Condition Name" pies visible
- Filter bar includes `exclude_condition_category` and `exclude_condition_name` dropdowns

Check Dry Run dashboard:
- Same 18 panels with "Would Be…" labels
- Variables bar has `exclude_condition_category` and `exclude_condition_name` but no `repository`

- [ ] **Step 3: Run existing tests to confirm nothing is broken**

```bash
python3 -m pytest tests/ -v
```
Expected: all tests pass (no ETL or schema logic was changed).

- [ ] **Step 4: Final commit if any fixups were needed, then tag done**

```bash
git status  # should be clean if no fixups needed
```
