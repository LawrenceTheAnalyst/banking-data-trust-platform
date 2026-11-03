# Banking Data Trust Platform — Synthetic Lab

A synthetic, portfolio-ready banking data engineering lab using Python, SQL, and PySpark.

## Scenario
Ubuntu Digital Bank receives core account data, payment transactions, and general-ledger postings. The lab generates a clean baseline, injects seven known failure modes, and provides validation/reconciliation patterns.

**Synthetic only.** No real banking/customer data is included.

## Quick start
```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
python src/generate_data.py --out data --days 30 --transactions 100000 --seed 42
```

This writes:
- `customers.csv`
- `accounts.csv`
- `transactions_clean.csv`
- `ledger_clean.csv`
- `transactions_injected.csv`
- `ledger_injected.csv`
- `injection_manifest.json`

Use the clean files as the baseline and injected files as the test fixture.

## Suggested flow
1. Land source files in Bronze with `ingest_batch_id`, `ingested_at`, `source_file`, and `source_row_number`.
2. Validate schemas and required fields.
3. Deduplicate by stable source event key; preserve duplicate evidence.
4. Normalize only explicitly approved values. Do not silently map unknown currency codes.
5. Quarantine invalid records with rule IDs and reasons.
6. Reconcile eligible transactions against ledger postings.
7. Publish Gold metrics and exception details.

## Run SQL
Load the generated CSVs into PostgreSQL (or adapt to your warehouse), then execute `sql/schema.sql` and `sql/quality_checks.sql`.

## Run PySpark tests
```bash
pip install pyspark pytest
pytest -q
```
PySpark tests use local mode and require a compatible Java runtime.

## Injection policy
The generator keeps the clean datasets intact and produces injected copies. The manifest records issue categories and affected identifiers. Some injected issues are event-level, some are dataset-level:
- duplicate transaction ID: append a repeated source event
- missing account reference: replace an existing account_id with a non-existent key
- late arrival: shift ingestion time while preserving event/transaction time
- reversal: add a reversal event referencing an original
- invalid currency: assign an unsupported code
- missing ledger entry: remove the corresponding posting
- daily spike: add a marked synthetic burst on a selected date

Injection labels are for evaluation only. In production, detection should not depend on these labels.

## Important semantics
- Amounts are decimal strings in source CSVs; use DECIMAL/Decimal, never binary float, for money.
- This lab models *transaction events*, not a complete double-entry accounting ledger.
- A reversal is a separate event that references the original. It is not automatically a duplicate.
- Ledger completeness checks must account for posting delays, settlement windows, currency, fees, and accounting rules.
- Spike detection is an alerting signal, not proof of fraud or data corruption.
