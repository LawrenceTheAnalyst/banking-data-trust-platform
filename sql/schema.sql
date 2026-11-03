CREATE TABLE IF NOT EXISTS customers (
  customer_id VARCHAR(16) PRIMARY KEY,
  created_date DATE NOT NULL,
  customer_segment VARCHAR(20) NOT NULL
);

CREATE TABLE IF NOT EXISTS accounts (
  account_id VARCHAR(16) PRIMARY KEY,
  customer_id VARCHAR(16) NOT NULL REFERENCES customers(customer_id),
  account_type VARCHAR(20) NOT NULL,
  currency_code CHAR(3) NOT NULL,
  account_status VARCHAR(12) NOT NULL
);

CREATE TABLE IF NOT EXISTS transactions_raw (
  transaction_id VARCHAR(32),
  account_id VARCHAR(16),
  customer_id VARCHAR(16),
  event_timestamp TIMESTAMPTZ,
  ingested_at TIMESTAMPTZ,
  transaction_type VARCHAR(20),
  direction VARCHAR(8),
  amount NUMERIC(18,2),
  currency_code VARCHAR(3),
  status VARCHAR(12),
  reversal_of_transaction_id VARCHAR(32),
  source_event_id VARCHAR(48),
  injection_label VARCHAR(40)
);

CREATE TABLE IF NOT EXISTS ledger_raw (
  ledger_entry_id VARCHAR(48),
  transaction_id VARCHAR(32),
  account_id VARCHAR(16),
  posting_timestamp TIMESTAMPTZ,
  signed_amount NUMERIC(18,2),
  currency_code VARCHAR(3),
  ledger_account VARCHAR(32),
  posting_status VARCHAR(12),
  source_event_id VARCHAR(48),
  injection_label VARCHAR(40)
);

CREATE TABLE IF NOT EXISTS dq_results (
  run_id VARCHAR(64) NOT NULL,
  rule_id VARCHAR(64) NOT NULL,
  entity_key VARCHAR(64),
  severity VARCHAR(12) NOT NULL,
  outcome VARCHAR(12) NOT NULL,
  details TEXT,
  evaluated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
