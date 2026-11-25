CREATE TABLE IF NOT EXISTS resource_metrics (
    id INTEGER PRIMARY KEY,
    recorded_at INTEGER NOT NULL,
    cpu_usage REAL CHECK (cpu_usage BETWEEN 0 AND 100),
    memory_usage REAL CHECK (memory_usage BETWEEN 0 AND 100),
    CHECK (cpu_usage IS NOT NULL OR memory_usage IS NOT NULL)
);

CREATE INDEX IF NOT EXISTS idx_resource_metrics_recorded_at
    ON resource_metrics (recorded_at);

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY,
    created_at INTEGER NOT NULL,
    category TEXT NOT NULL CHECK (category IN ('files', 'processes', 'system')),
    operation TEXT NOT NULL,
    description TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('success', 'error'))
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY NOT NULL,
    value TEXT NOT NULL
);
