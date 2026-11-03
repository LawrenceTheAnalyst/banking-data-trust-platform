import pytest
pyspark = pytest.importorskip("pyspark")
from pyspark.sql import SparkSession
from pyspark.sql import functions as F
from src.pyspark_quality import quality_findings

@pytest.fixture(scope="module")
def spark():
    s = SparkSession.builder.master("local[2]").appName("banking-dq-tests").getOrCreate()
    yield s
    s.stop()

def test_detects_core_injected_issues(spark):
    tx = spark.createDataFrame([
      ("T1","A1","2026-09-01 00:00:00","2026-09-01 00:01:00","ZAR","SETTLED",""),
      ("T1","A1","2026-09-01 00:00:00","2026-09-01 00:01:00","ZAR","SETTLED",""),
      ("T2","AX","2026-09-01 00:00:00","2026-09-05 03:00:00","ZRX","SETTLED",""),
      ("T3","A1","2026-09-01 00:00:00","2026-09-01 00:02:00","ZAR","SETTLED","NOPE")
    ], ["transaction_id","account_id","event_timestamp","ingested_at","currency_code","status","reversal_of_transaction_id"])
    tx = tx.withColumn("event_timestamp", F.to_timestamp("event_timestamp")) \
           .withColumn("ingested_at", F.to_timestamp("ingested_at"))
    accounts = spark.createDataFrame([("A1",)], ["account_id"])
    ledger = spark.createDataFrame([("T1","POSTED")], ["transaction_id","posting_status"])
    findings = quality_findings(tx, accounts, ledger)
    assert findings["duplicate_transaction_id"].filter("transaction_id='T1'").count() == 1
    assert findings["missing_account_reference"].filter("transaction_id='T2'").count() == 1
    assert findings["late_arrival"].filter("transaction_id='T2'").count() == 1
    assert findings["invalid_currency_code"].filter("transaction_id='T2'").count() == 1
    assert findings["missing_original_for_reversal"].filter("transaction_id='T3'").count() == 1
    assert findings["missing_ledger_entry"].filter("transaction_id='T2'").count() == 1
