-- DT-RAM TimescaleDB bootstrap schema.
CREATE EXTENSION IF NOT EXISTS timescaledb;

CREATE TABLE IF NOT EXISTS nodes (
  node_id TEXT PRIMARY KEY,
  location TEXT,
  cpu_total DOUBLE PRECISION,
  memory_total_mb DOUBLE PRECISION,
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS node_metrics (
  ts TIMESTAMPTZ NOT NULL,
  node_id TEXT NOT NULL,
  cpu DOUBLE PRECISION,
  memory DOUBLE PRECISION,
  network_in DOUBLE PRECISION,
  network_out DOUBLE PRECISION
);
SELECT create_hypertable('node_metrics', 'ts', if_not_exists => TRUE);

CREATE TABLE IF NOT EXISTS twin_fidelity (
  ts TIMESTAMPTZ NOT NULL,
  node_id TEXT NOT NULL,
  fidelity DOUBLE PRECISION,
  autonomy_level TEXT
);
SELECT create_hypertable('twin_fidelity', 'ts', if_not_exists => TRUE);

CREATE TABLE IF NOT EXISTS decisions (
  decision_id TEXT PRIMARY KEY,
  policy_version TEXT,
  action_type TEXT,
  service_id TEXT,
  source_node TEXT,
  destination_node TEXT,
  approved BOOLEAN,
  reasons TEXT,
  created_at TIMESTAMPTZ DEFAULT now()
);
