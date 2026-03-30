CREATE TABLE IF NOT EXISTS audit_events (
    id                             BIGINT PRIMARY KEY,
    created_at                     TIMESTAMPTZ NOT NULL,
    action                         VARCHAR(20),
    is_dry_run                     BOOLEAN NOT NULL DEFAULT FALSE,
    package_type                   VARCHAR(50),
    package_name                   VARCHAR(255),
    package_version                VARCHAR(100),
    package_url                    TEXT,
    reason                         TEXT,
    event_origin                   VARCHAR(255),
    curated_repository_name        VARCHAR(255),
    curated_repository_server_name VARCHAR(255),
    curated_project                VARCHAR(255),
    username                       VARCHAR(255),
    user_mail                      VARCHAR(255),
    origin_repository_name         VARCHAR(255),
    origin_repository_server_name  VARCHAR(255),
    origin_project                 VARCHAR(255),
    public_repo_url                TEXT,
    public_repo_name               VARCHAR(255)
);

CREATE INDEX IF NOT EXISTS idx_audit_events_created_at   ON audit_events (created_at);
CREATE INDEX IF NOT EXISTS idx_audit_events_action        ON audit_events (action);
CREATE INDEX IF NOT EXISTS idx_audit_events_is_dry_run    ON audit_events (is_dry_run);
CREATE INDEX IF NOT EXISTS idx_audit_events_package_type  ON audit_events (package_type);
CREATE INDEX IF NOT EXISTS idx_audit_events_username      ON audit_events (username);

CREATE TABLE IF NOT EXISTS event_policies (
    id            SERIAL PRIMARY KEY,
    event_id      BIGINT NOT NULL REFERENCES audit_events(id) ON DELETE CASCADE,
    policy_name   VARCHAR(255),
    rule_name     VARCHAR(255),
    policy_action VARCHAR(50),
    cve_id        VARCHAR(50),
    severity      VARCHAR(20)
);

CREATE INDEX IF NOT EXISTS idx_event_policies_event_id    ON event_policies (event_id);
CREATE INDEX IF NOT EXISTS idx_event_policies_policy_name ON event_policies (policy_name);
