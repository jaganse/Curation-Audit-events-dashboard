# Curation Audit Events Dashboard — Design Spec

**Date:** 2026-03-27
**Status:** Approved

---

## Context

JFrog Curation exposes audit events via REST API — every package download decision (approved or blocked) is recorded with metadata: which package, which user, which policy triggered, which repository. The exported `curation-audit-evnts.json` shows this data but offers no visual analysis.

The goal is a local dashboard that gives engineers and security teams instant visibility into what Curation is enforcing, which policies are firing most, and which packages are being blocked — updated daily via automated ETL.

---

## Architecture

**Stack:** Python ETL → PostgreSQL 16 → Grafana OSS
**Deployment:** Docker Compose (local machine)
**Scheduling:** Host `cron` triggers the ETL container daily

```
JFrog Curation API
    │  GET /xray/api/v1/curation/audit/packages?dry_run=false (paginated, up to 2000/req)
    │  GET /xray/api/v1/curation/audit/packages?dry_run=true  (paginated, up to 2000/req)
    ▼
Python ETL (fetch_events.py)
    │  Paginates until all results fetched
    │  Normalizes policies[] array
    │  Upserts via ON CONFLICT (id) DO UPDATE
    ▼
PostgreSQL
    │  audit_events table
    │  event_policies table
    ▼
Grafana (localhost:3000)
    ├── Real Events Dashboard
    └── Dry Run Dashboard
```

---

## Data Model

### `audit_events`

| Column | Type | Notes |
|---|---|---|
| `id` | BIGINT PK | From JFrog API — natural dedup key |
| `created_at` | TIMESTAMPTZ | Indexed |
| `action` | VARCHAR | `'approved'` or `'blocked'` — indexed |
| `is_dry_run` | BOOLEAN | `false` = real enforcement, `true` = simulation — indexed |
| `package_type` | VARCHAR | `'npm'`, `'pypi'`, `'maven'`, etc. — indexed |
| `package_name` | VARCHAR | |
| `package_version` | VARCHAR | |
| `package_url` | TEXT | |
| `reason` | TEXT | Human-readable decision reason |
| `event_origin` | VARCHAR | e.g. `'Download to repository'` |
| `curated_repository_name` | VARCHAR | |
| `curated_repository_server_name` | VARCHAR | |
| `curated_project` | VARCHAR | |
| `username` | VARCHAR | Indexed |
| `user_mail` | VARCHAR | |
| `origin_repository_name` | VARCHAR | |
| `origin_repository_server_name` | VARCHAR | |
| `origin_project` | VARCHAR | |
| `public_repo_url` | TEXT | |
| `public_repo_name` | VARCHAR | |

### `event_policies`

Normalized from the `policies[]` array on each event. One event may produce zero or more rows here (blocked events typically have policies; approved events have `null`).

> **Note:** The sample data (`curation-audit-evnts.json`) contains only approved events, so `policies` is `null` in all records. The schema below is based on the JFrog Curation API documentation and common policy object shapes. Confirm and adjust column names once real blocked events are observed.

| Column | Type | Notes |
|---|---|---|
| `id` | SERIAL PK | |
| `event_id` | BIGINT FK | → `audit_events.id` |
| `policy_name` | VARCHAR | |
| `rule_name` | VARCHAR | |
| `policy_action` | VARCHAR | `'block'`, `'bypass'`, `'waive'` |
| `cve_id` | VARCHAR | Nullable |
| `severity` | VARCHAR | Nullable |

---

## ETL Design (`etl/fetch_events.py`)

**API endpoint:**
```
GET {JFROG_URL}/xray/api/v1/curation/audit/packages
```

**Query parameters used:**

| Param | Value | Notes |
| --- | --- | --- |
| `dry_run` | `false` / `true` | Two separate fetch passes per ETL run |
| `num_of_rows` | `2000` | Maximum allowed for JSON; minimises API round-trips |
| `offset` | incremented per page | Pagination cursor |
| `include_total` | `true` | Required to receive `total_count` in response metadata |
| `created_at_start` | RFC 3339 | now − LOOKBACK_DAYS |
| `created_at_end` | RFC 3339 | now |
| `order_by` | `id` | Stable ordering for consistent pagination |
| `direction` | `asc` | Ascending so offset-based paging is deterministic |

**Inputs** (from `.env`):
- `JFROG_URL` — base URL of the JFrog platform (e.g. `https://myinstance.jfrog.io`)
- `JFROG_TOKEN` — API token (Identity Token or Access Token)
- `DATABASE_URL` — PostgreSQL connection string
- `LOOKBACK_DAYS` — how far back to fetch on each run (default: `2` to catch any late-arriving events; set to a large value like `365` for the initial backfill run)

**Algorithm:**
1. Calculate `created_at_start` = now − LOOKBACK_DAYS, `created_at_end` = now
2. For each mode (`dry_run=false`, `dry_run=true`):
   - First request: include `include_total=true` to learn `total_count`
   - Loop: GET with current `offset`, increment by 2000 until `offset >= total_count`
   - For each event: upsert into `audit_events` (set `is_dry_run` accordingly)
   - For each event with non-null `policies`: delete existing `event_policies` rows for that `event_id`, then insert fresh rows
3. Log summary: events fetched, upserted, policies inserted

**Idempotency:** `ON CONFLICT (id) DO UPDATE SET ...all columns...` ensures re-runs are safe. Policy rows are delete-then-insert per event to stay in sync with API.

---

## Grafana Dashboards

Both dashboards are provisioned as JSON files (no manual UI setup needed).

### Shared Dashboard Variables (Grafana template variables)
- **Time range** — built-in Grafana time picker
- `$package_type` — multi-value dropdown populated from `SELECT DISTINCT package_type FROM audit_events`
- `$repository` — dropdown from `SELECT DISTINCT curated_repository_name FROM audit_events`

### Real Events Dashboard (`is_dry_run = false`)

| Panel | Type | Query focus |
|---|---|---|
| Total Events | Stat | COUNT(*) in time range |
| Blocked | Stat | COUNT(*) WHERE action='blocked' |
| Approved | Stat | COUNT(*) WHERE action='approved' |
| Unique Packages | Stat | COUNT(DISTINCT package_name) |
| Blocked vs Approved over time | Bar chart (stacked) | GROUP BY date_trunc('day', created_at), action |
| Top Blocked Packages | Table | WHERE action='blocked' GROUP BY package_name ORDER BY count DESC |
| Policy Breakdown | Bar chart | JOIN event_policies, GROUP BY policy_name |
| User Activity | Table | GROUP BY username ORDER BY count DESC |
| Package Type Split | Pie chart | GROUP BY package_type |

### Dry Run Dashboard (`is_dry_run = true`)

Same panel layout but queries filter `WHERE is_dry_run = true`. Focus shifts from enforcement to simulation — "what would have been blocked."

---

## Project Structure

```
curation-audit-dashboard/
├── docker-compose.yml
├── .env.example
├── .gitignore                         # includes .env, .superpowers/
├── etl/
│   ├── fetch_events.py
│   └── requirements.txt               # requests, psycopg2-binary, python-dotenv
├── postgres/
│   └── init.sql                       # CREATE TABLE + indexes
└── grafana/
    └── provisioning/
        ├── datasources/
        │   └── postgres.yml           # auto-wires Grafana → Postgres
        └── dashboards/
            ├── dashboards.yml         # tells Grafana to load from this dir
            ├── real-events.json
            └── dry-run.json
```

---

## Docker Compose Services

| Service | Image | Port | Volume |
|---|---|---|---|
| `postgres` | `postgres:16-alpine` | 5432 (internal) | `postgres_data:/var/lib/postgresql/data` |
| `grafana` | `grafana/grafana-oss:latest` | `3000:3000` | `grafana_data:/var/lib/grafana`, `./grafana/provisioning:/etc/grafana/provisioning` |

The ETL runs as a one-shot command (`docker compose run --rm etl`) rather than a long-running service, triggered by host cron:

```cron
0 6 * * * cd /path/to/project && docker compose run --rm etl
```

---

## Verification

1. `docker compose up -d` — postgres and grafana start
2. `LOOKBACK_DAYS=365 docker compose run --rm etl` — initial backfill; subsequent runs use the default (2 days)
3. Open `http://localhost:3000` — Grafana loads with both dashboards pre-provisioned
4. Real Events dashboard shows KPI tiles, trend chart, top packages, policy breakdown, user activity
5. Dry Run dashboard shows simulated policy hits
6. Re-run ETL — no duplicate rows in postgres (`SELECT COUNT(*) FROM audit_events` stays stable)
7. Change time range in Grafana — all panels update correctly
