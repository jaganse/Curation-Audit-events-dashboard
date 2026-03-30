# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Purpose

This project is intended to be a dashboard for visualizing JFrog Curation audit events. The data source is the JFrog Artifactory Curation API, with an example export in `curation-audit-evnts.json`.

**No application code exists yet.** This is a greenfield project built around the audit events data.

## Data Source

### File: `curation-audit-evnts.json`

A paginated API response from the JFrog Curation audit events endpoint. Top-level structure:

```json
{
  "data": [ /* array of audit event records */ ],
  "meta": {
    "total_count": 166,
    "result_count": 100,
    "next_offset": 100,
    "order_by": "id",
    "direction": "desc",
    "num_of_rows": 100,
    "offset": 0,
    "created_at_start": "2026-03-05T00:00:00Z",
    "created_at_end": "2026-03-10T23:59:00Z"
  }
}
```

### Audit Event Record Schema

| Field | Type | Description |
|-------|------|-------------|
| `id` | number | Unique event ID |
| `created_at` | ISO 8601 string | Timestamp of the event |
| `action` | string | Curation decision: `"approved"`, `"blocked"`, etc. |
| `package_type` | string | Package ecosystem: `"npm"`, `"pypi"`, etc. |
| `package_name` | string | Name of the package |
| `package_version` | string | Version string |
| `package_url` | string | Direct URL to the package artifact |
| `reason` | string | Human-readable reason for the decision |
| `event_origin` | string | How the event was triggered (e.g. `"Download to repository"`) |
| `curated_repository_name` | string | Target repository in Artifactory |
| `curated_repository_server_name` | string | Server hosting the target repo |
| `curated_project` | string | Artifactory project (e.g. `"default"`) |
| `username` | string | User who triggered the event |
| `user_mail` | string | Email of the triggering user |
| `origin_repository_name` | string | Source repository |
| `origin_repository_server_name` | string | Server hosting the source repo |
| `origin_project` | string | Artifactory project of the source |
| `public_repo_url` | string | Upstream public registry URL |
| `public_repo_name` | string | Human-readable upstream registry name |
| `policies` | array or null | Policies that triggered the decision |

### Key Observations
- The `meta.total_count` (166) exceeds `meta.result_count` (100), so full data requires pagination via `offset`.
- `policies` is `null` for approved events; blocked events would populate this array with policy violation details.
- The sample data covers a narrow time window and contains only `approved` events for `npm` packages.
