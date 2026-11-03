from pyspark.sql import functions as F, Window

ALLOWED_CURRENCIES = ["ZAR", "USD", "GBP", "EUR"]

def quality_findings(tx, accounts, ledger, late_hours=24):
    """Return named finding DataFrames. Input data is expected to include parsed timestamps."""
    duplicate_ids = (tx.groupBy("transaction_id").count()
                     .filter(F.col("count") > 1).select("transaction_id", "count"))
    missing_accounts = (tx.join(accounts.select("account_id"), "account_id", "left_anti")
                        .select("transaction_id", "account_id"))
    late = (tx.filter(F.col("ingested_at") >
                      F.expr(f"event_timestamp + INTERVAL {int(late_hours)} HOURS"))
            .select("transaction_id", "event_timestamp", "ingested_at"))
    bad_currency = tx.filter(~F.col("currency_code").isin(ALLOWED_CURRENCIES)) \
                     .select("transaction_id", "currency_code")
    reversal_refs = (tx.filter(F.col("reversal_of_transaction_id").isNotNull() &
                               (F.col("reversal_of_transaction_id") != ""))
                     .alias("r").join(tx.select(F.col("transaction_id").alias("original_id")).alias("o"),
                                      F.col("r.reversal_of_transaction_id")==F.col("o.original_id"),
                                      "left_anti")
                     .select(F.col("r.transaction_id").alias("transaction_id"),
                             F.col("r.reversal_of_transaction_id").alias("missing_original_id")))
    posted = ledger.filter(F.col("posting_status") == "POSTED").select("transaction_id").distinct()
    missing_ledger = (tx.filter(F.col("status") == "SETTLED")
                      .join(posted, "transaction_id", "left_anti")
                      .select("transaction_id"))
    daily = tx.withColumn("event_date", F.to_date("event_timestamp")) \
              .groupBy("event_date").agg(F.count("*").alias("tx_count"))
    # Starter global threshold only. Production use seasonality-aware history and robust statistics.
    stats = daily.agg(F.avg("tx_count").alias("avg"), F.stddev_pop("tx_count").alias("sd")).first()
    avg = stats["avg"] or 0
    sd = stats["sd"] or 0
    spikes = daily.filter(F.col("tx_count") > F.lit(avg + 3*sd))
    return {
        "duplicate_transaction_id": duplicate_ids,
        "missing_account_reference": missing_accounts,
        "late_arrival": late,
        "invalid_currency_code": bad_currency,
        "missing_original_for_reversal": reversal_refs,
        "missing_ledger_entry": missing_ledger,
        "daily_volume_spike_candidates": spikes
    }
