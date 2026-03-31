# Colleague Dashboard Parity — Design Spec

**Date:** 2026-03-31
**Status:** Approved

## Context

A colleague shared a more advanced Grafana dashboard (`ansys-curation-grafana-dashboard.jpg`) built on the same JFrog Curation audit events API. It surfaces several high-value metrics our dashboard doesn't have yet: waived package tracking, overall and per-ecosystem block rate KPIs, condition category/name breakdowns, and ecosystem-level grouped charts. This spec covers bringing our dashboard to parity with that design.

Applies to **both** the Real Events and Dry Run dashboards.

---

## What Is Being Added

### 1. Waived Action Support

`"waived"` is a valid `action` value in the JFrog API (alongside `"approved"` and `"blocked"`). No schema change is needed — `action` is already `VARCHAR(20)`. The ETL already stores whatever value arrives. Dashboard queries simply add `waived` as a third action category.

### 2. New Stats (2 panels)

- **% Blocked** — `ROUND(100.0 * SUM(CASE WHEN action='blocked' THEN 1 ELSE 0 END) / COUNT(*), 1)` — orange stat panel
- **Waived** — `COUNT(*) WHERE action='waived'` — yellow/gold stat panel

The stats row expands from 4 panels to 6: Total Events · % Blocked · Blocked · Approved · Waived · Unique Packages (each `w=4` across the 24-column grid).

### 3. Updated Timeseries

The existing "Blocked vs Approved Over Time" timeseries gets a third series: **Waived** (yellow). Same `$__timeGroupAlias(created_at,'1d')` pattern, adds a `WHERE action='waived'` query as `refId: "C"`.

### 4. Ecosystem Breakdown Row (2 new panels)

**Panel A — Approved / Blocked / Waived by Ecosystem** (grouped bar chart, `w=12`)

Single query returning multiple value columns — Grafana's `barchart` panel type renders these as a grouped bar automatically:

```sql
SELECT package_type,
  SUM(CASE WHEN action='approved' THEN 1 ELSE 0 END) AS approved,
  SUM(CASE WHEN action='blocked'  THEN 1 ELSE 0 END) AS blocked,
  SUM(CASE WHEN action='waived'   THEN 1 ELSE 0 END) AS waived
FROM audit_events
WHERE is_dry_run = false AND $__timeFilter(created_at) ...
GROUP BY package_type
ORDER BY (approved + blocked + waived) DESC
```

Uses `_barchart()` with `orientation="auto"` (vertical bars, one group per ecosystem).

**Panel B — % Blocked by Ecosystem** (horizontal bar chart, `w=12`)

Single query: `SELECT package_type, ROUND(100.0 * SUM(CASE WHEN action='blocked' THEN 1 ELSE 0 END) / COUNT(*), 1) AS pct_blocked FROM audit_events ... GROUP BY package_type ORDER BY pct_blocked DESC`. Uses `_barchart()` with `orientation="horizontal"`.

### 5. Condition Analysis Row (2 new pie charts)

Uses `event_policies JOIN audit_events`. Both pies apply the new exclude-variable filters.

**Panel C — Blocked by Condition Category** (`w=8`): groups by `ep.condition_category`

**Panel D — Blocked by Condition Name** (`w=8`): groups by `ep.condition_name`

SQL pattern:
```sql
SELECT ep.condition_category, COUNT(*) AS count
FROM audit_events ae
JOIN event_policies ep ON ae.id = ep.event_id
WHERE ae.is_dry_run = false
  AND ae.action = 'blocked'
  AND $__timeFilter(ae.created_at)
  AND ('$package_type' = ANY(ARRAY['', 'All']) OR ae.package_type = '$package_type')
  AND ('$repository'   = ANY(ARRAY['', 'All']) OR ae.curated_repository_name = '$repository')
  AND (ep.condition_category != '$exclude_condition_category'
       OR '$exclude_condition_category' = '')
GROUP BY ep.condition_category
ORDER BY count DESC
```

### 6. Waived by Ecosystem Pie (1 new panel)

`WHERE action = 'waived'`, `GROUP BY package_type`. Placed alongside Policy Breakdown and User Activity (`w=8` each in a 3-column row).

### 7. User Activity Table Update

Adds a `waived_count` column: `SUM(CASE WHEN action = 'waived' THEN 1 ELSE 0 END)`.

### 8. New Filter Variables (2)

Added to both dashboards:

```python
_var("exclude_condition_category", "Exclude Condition Category",
     "SELECT '' AS condition_category "
     "UNION SELECT DISTINCT condition_category FROM event_policies "
     "WHERE condition_category IS NOT NULL ORDER BY 1")

_var("exclude_condition_name", "Exclude Condition Name",
     "SELECT '' AS condition_name "
     "UNION SELECT DISTINCT condition_name FROM event_policies "
     "WHERE condition_name IS NOT NULL ORDER BY 1")
```

Default: empty string (nothing excluded). Users set these to `"N/A"` to strip noise from condition pies.

---

## Dashboard Layout (Real Events)

```
Row y=0  h=4  [Total Events w=4][% Blocked w=4][Blocked w=4][Approved w=4][Waived w=4][Unique Pkgs w=4]
Row y=4  h=8  [Blocked / Approved / Waived Over Time — full width w=24]
Row y=12 h=8  [Approved/Blocked/Waived by Ecosystem w=12][% Blocked by Ecosystem w=12]
Row y=20 h=8  [Top Blocked Packages w=8][Blocked by Condition Category w=8][Blocked by Condition Name w=8]
Row y=28 h=8  [Policy Breakdown w=8][Waived by Ecosystem w=8][User Activity w=8]
Row y=36       [High-Persistence Users h=4 w=6][Persistent Blocked Packages h=8 w=18]  (existing, pushed down)
Row y=44 h=8  [Download Sessions Over Time w=24]  (existing, pushed down)
```

The Dry Run dashboard mirrors this layout but:
- Uses `is_dry_run = true`
- Omits the `repository` filter variable (as today)
- Labels adjusted: "Would Be Blocked", "Would Be Waived", etc.
- Condition pies use `ae.is_dry_run = true`

---

## Implementation

### Files changed

| File | Change |
|---|---|
| `scripts/generate_dashboards.py` | Add `_barchart()` builder; add 7 new panels + updated timeseries/stats/user-activity to `real_events()` and `dry_run()`; add 2 new `_var()` entries |
| `grafana/provisioning/dashboards/real-events.json` | Regenerated |
| `grafana/provisioning/dashboards/dry-run.json` | Regenerated |

No ETL, schema, or Docker changes required.

### New `_barchart()` builder

Takes a single SQL string — Grafana's `barchart` panel renders multiple value columns as grouped bars automatically. Same signature style as `_pie()` and `_table()`.

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

---

## Verification

1. Run `python3 scripts/generate_dashboards.py` — should print both files written, no errors
2. `docker compose up -d postgres grafana`
3. Open `http://localhost:3000` — Curation Audit → Real Events:
   - Stats row shows 6 panels including % Blocked and Waived
   - Ecosystem row renders two bar charts
   - Condition pies render (may show empty until blocked events with policies are ingested)
   - Exclude variables appear in the filter bar
4. Verify Dry Run dashboard has the same additions with dry-run labels
5. Run `pytest tests/` — all existing tests pass (no logic changes, only dashboard JSON)
