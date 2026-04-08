-- Migration: add condition_name and condition_category to event_policies
-- Run this against existing databases where init.sql has already executed.
--
-- Usage:
--   docker compose exec postgres psql -U audit -d audit \
--     -f /path/to/migrations/001_add_condition_fields.sql
--
-- Safe to re-run (ADD COLUMN IF NOT EXISTS is idempotent).

ALTER TABLE event_policies
    ADD COLUMN IF NOT EXISTS condition_name     VARCHAR(255),
    ADD COLUMN IF NOT EXISTS condition_category VARCHAR(100);
