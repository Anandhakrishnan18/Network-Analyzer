-- Relational Schema for Internet Quality Analyzer & Connection Troubleshooter
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS test_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp_utc TEXT NOT NULL,         -- ISO 8601 UTC format: YYYY-MM-DDTHH:MM:SS.fZ
    trigger_type TEXT NOT NULL,          -- 'manual', 'periodic', 'scheduled'
    overall_status TEXT NOT NULL,        -- 'healthy', 'warning', 'critical', 'insufficient_data'
    summary TEXT,
    total_targets INTEGER NOT NULL,
    duration_seconds REAL NOT NULL,
    gateway_ip TEXT,
    local_ip TEXT
);

CREATE TABLE IF NOT EXISTS metric_samples (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    test_run_id INTEGER NOT NULL,
    target_id TEXT NOT NULL,
    target_name TEXT NOT NULL,
    target_type TEXT NOT NULL,           -- 'gateway', 'dns_resolver', 'external_host'
    target_address TEXT NOT NULL,
    target_port INTEGER,
    latency_avg_ms REAL,
    latency_min_ms REAL,
    latency_max_ms REAL,
    latency_median_ms REAL,
    jitter_ms REAL,
    packet_loss_pct REAL NOT NULL,
    probes_sent INTEGER NOT NULL,
    probes_received INTEGER NOT NULL,
    dns_lookup_time_ms REAL,
    tcp_handshake_time_ms REAL,
    status TEXT NOT NULL,                -- 'success', 'degraded', 'failed'
    error_message TEXT,
    samples_json TEXT,                  -- Serialized array of individual RTTs
    FOREIGN KEY (test_run_id) REFERENCES test_runs(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS dns_benchmarks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    test_run_id INTEGER NOT NULL,
    resolver_name TEXT NOT NULL,
    resolver_ip TEXT NOT NULL,
    domain TEXT NOT NULL,
    avg_ms REAL,
    min_ms REAL,
    max_ms REAL,
    status TEXT NOT NULL,
    samples_json TEXT,
    FOREIGN KEY (test_run_id) REFERENCES test_runs(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS diagnostic_findings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    test_run_id INTEGER NOT NULL,
    rule_id TEXT NOT NULL,
    severity TEXT NOT NULL,              -- 'info', 'warning', 'critical'
    symptom TEXT NOT NULL,
    evidence_json TEXT NOT NULL,         -- Structured quantitative measurements
    possible_causes_json TEXT NOT NULL,  -- JSON array of explanations
    recommendations_json TEXT NOT NULL,  -- JSON array of actionable steps
    confidence TEXT NOT NULL,            -- 'High', 'Moderate', 'Low'
    limitations TEXT NOT NULL,
    FOREIGN KEY (test_run_id) REFERENCES test_runs(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    test_run_id INTEGER,
    timestamp_utc TEXT NOT NULL,
    metric_name TEXT NOT NULL,
    threshold_value REAL NOT NULL,
    observed_value REAL NOT NULL,
    message TEXT NOT NULL,
    FOREIGN KEY (test_run_id) REFERENCES test_runs(id) ON DELETE SET NULL
);

-- Performance Indexes
CREATE INDEX IF NOT EXISTS idx_test_runs_timestamp ON test_runs(timestamp_utc);
CREATE INDEX IF NOT EXISTS idx_metric_samples_run_id ON metric_samples(test_run_id);
CREATE INDEX IF NOT EXISTS idx_metric_samples_target ON metric_samples(target_id);
CREATE INDEX IF NOT EXISTS idx_findings_run_id ON diagnostic_findings(test_run_id);
CREATE INDEX IF NOT EXISTS idx_dns_benchmarks_run_id ON dns_benchmarks(test_run_id);
CREATE INDEX IF NOT EXISTS idx_alerts_timestamp ON alerts(timestamp_utc);
