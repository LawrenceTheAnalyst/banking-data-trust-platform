-- Execute against transactions_raw, accounts, ledger_raw after loading CSV files.
-- Rule DQ-TX-001: duplicate transaction IDs (duplicate event semantics may require source_event_id too)
SELECT transaction_id, COUNT(*) AS row_count
FROM transactions_raw
GROUP BY transaction_id
HAVING COUNT(*) > 1;

-- Rule DQ-TX-002: missing/nonexistent account reference
SELECT t.transaction_id, t.account_id
FROM transactions_raw t
LEFT JOIN accounts a ON a.account_id = t.account_id
WHERE a.account_id IS NULL;

-- Rule DQ-TX-003: late arrivals, here defined as >24h from event to ingestion
SELECT transaction_id, event_timestamp, ingested_at,
       ingested_at - event_timestamp AS ingestion_lag
FROM transactions_raw
WHERE ingested_at > event_timestamp + INTERVAL '24 hours';

-- Rule DQ-TX-004: unsupported currency code (adapt allowed set to approved reference data)
SELECT transaction_id, currency_code
FROM transactions_raw
WHERE currency_code NOT IN ('ZAR','USD','GBP','EUR');

-- Rule DQ-TX-005: reversal reference integrity
SELECT r.transaction_id, r.reversal_of_transaction_id
FROM transactions_raw r
LEFT JOIN transactions_raw o
  ON o.transaction_id = r.reversal_of_transaction_id
WHERE r.reversal_of_transaction_id IS NOT NULL
  AND r.reversal_of_transaction_id <> ''
  AND o.transaction_id IS NULL;

-- Rule DQ-GL-001: settled transactions with no posted ledger entry.
-- This simplified check assumes one control posting per settled event.
SELECT t.transaction_id
FROM transactions_raw t
LEFT JOIN ledger_raw l
  ON l.transaction_id = t.transaction_id
 AND l.posting_status = 'POSTED'
WHERE t.status = 'SETTLED'
GROUP BY t.transaction_id
HAVING COUNT(l.ledger_entry_id) = 0;

-- Rule DQ-TX-006: daily volume anomaly candidate.
-- Baseline threshold should be calibrated by weekday, product, and source; this is a starter.
WITH daily AS (
  SELECT CAST(event_timestamp AS DATE) AS event_date, COUNT(*) AS tx_count
  FROM transactions_raw
  GROUP BY CAST(event_timestamp AS DATE)
), stats AS (
  SELECT AVG(tx_count) AS avg_daily,
         STDDEV_POP(tx_count) AS sd_daily
  FROM daily
)
SELECT d.event_date, d.tx_count, s.avg_daily, s.sd_daily
FROM daily d CROSS JOIN stats s
WHERE d.tx_count > s.avg_daily + 3 * COALESCE(s.sd_daily, 0);
