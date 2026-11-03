from __future__ import annotations
import argparse, csv, json, random
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

CURRENCIES = ["ZAR", "USD", "GBP", "EUR"]
STATUSES = ["SETTLED", "PENDING", "FAILED"]

def iso(dt): return dt.isoformat(timespec="seconds")
def money(v): return f"{Decimal(v):.2f}"

def write_csv(path: Path, rows, columns):
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=columns)
        w.writeheader()
        w.writerows(rows)

def generate(out: Path, days: int, n_tx: int, seed: int):
    rng = random.Random(seed)
    out.mkdir(parents=True, exist_ok=True)
    start = datetime(2026, 9, 1, tzinfo=timezone.utc)
    customers, accounts = [], []
    n_customers = max(1000, n_tx // 10)
    for i in range(1, n_customers + 1):
        customers.append({"customer_id": f"C{i:07d}", "created_date": (start.date()-timedelta(days=rng.randint(30,1500))).isoformat(),
                          "customer_segment": rng.choice(["RETAIL","SME","PREMIUM"])})
    for i in range(1, max(1500, int(n_customers*1.5)) + 1):
        accounts.append({"account_id": f"A{i:08d}", "customer_id": f"C{rng.randint(1,n_customers):07d}",
                         "account_type": rng.choice(["CHEQUE","SAVINGS","BUSINESS"]),
                         "currency_code": rng.choice(CURRENCIES), "account_status": "ACTIVE"})
    account_by_id = {a["account_id"]: a for a in accounts}
    transactions, ledger = [], []
    tx_count = max(1, n_tx)
    for i in range(1, tx_count+1):
        acct = rng.choice(accounts)
        day = rng.randrange(days)
        event_dt = start + timedelta(days=day, seconds=rng.randrange(86400))
        txid = f"T{i:010d}"
        amount = Decimal(rng.randint(100, 2500000)) / Decimal("100")
        direction = rng.choice(["DEBIT","CREDIT"])
        signed = amount if direction == "CREDIT" else -amount
        status = rng.choices(STATUSES, weights=[85,10,5])[0]
        row = {
            "transaction_id": txid, "account_id": acct["account_id"],
            "customer_id": acct["customer_id"], "event_timestamp": iso(event_dt),
            "ingested_at": iso(event_dt + timedelta(minutes=rng.randint(0,12))),
            "transaction_type": rng.choice(["CARD","EFT","ATM","TRANSFER"]),
            "direction": direction, "amount": money(amount), "currency_code": acct["currency_code"],
            "status": status, "reversal_of_transaction_id": "", "source_event_id": f"EV-{txid}",
            "injection_label": ""
        }
        transactions.append(row)
        # Only settled original events receive a simple modeled ledger posting.
        if status == "SETTLED":
            ledger.append({
                "ledger_entry_id": f"L{i:010d}", "transaction_id": txid, "account_id": acct["account_id"],
                "posting_timestamp": iso(event_dt + timedelta(minutes=rng.randint(1,60))),
                "signed_amount": money(signed), "currency_code": acct["currency_code"],
                "ledger_account": "CUSTOMER_CONTROL", "posting_status": "POSTED",
                "source_event_id": f"GL-{txid}", "injection_label": ""
            })

    clean_tx = [dict(x) for x in transactions]
    clean_gl = [dict(x) for x in ledger]
    bad_tx = [dict(x) for x in transactions]
    bad_gl = [dict(x) for x in ledger]
    manifest = {"seed": seed, "days": days, "baseline_transactions": len(clean_tx), "baseline_ledger": len(clean_gl),
                "injections": {}}

    # 1 Duplicate transaction ID: append duplicate event with same transaction and source event identifiers.
    duplicate = dict(rng.choice(bad_tx))
    duplicate["injection_label"] = "DUPLICATE_TRANSACTION_ID"
    bad_tx.append(duplicate)
    manifest["injections"]["duplicate_transaction_id"] = [duplicate["transaction_id"]]

    # 2 Missing/nonexistent account reference.
    target = next(x for x in bad_tx if not x["injection_label"])
    target["account_id"] = "A99999999"
    target["injection_label"] = "MISSING_ACCOUNT_REFERENCE"
    manifest["injections"]["missing_account_reference"] = [target["transaction_id"]]

    # 3 Late arrival: ingestion timestamp far beyond defined 24-hour SLA.
    target = next(x for x in bad_tx if not x["injection_label"])
    event = datetime.fromisoformat(target["event_timestamp"])
    target["ingested_at"] = iso(event + timedelta(days=4, hours=3))
    target["injection_label"] = "LATE_ARRIVAL"
    manifest["injections"]["late_arrival"] = [target["transaction_id"]]

    # 4 Reversal event: separately keyed transaction references an existing settled original.
    original = next(x for x in bad_tx if x["status"] == "SETTLED" and not x["injection_label"])
    reversal = dict(original)
    reversal["transaction_id"] = "R-" + original["transaction_id"]
    reversal["source_event_id"] = "EV-R-" + original["transaction_id"]
    reversal["event_timestamp"] = iso(datetime.fromisoformat(original["event_timestamp"]) + timedelta(hours=2))
    reversal["ingested_at"] = iso(datetime.fromisoformat(reversal["event_timestamp"]) + timedelta(minutes=2))
    reversal["direction"] = "CREDIT" if original["direction"] == "DEBIT" else "DEBIT"
    reversal["status"] = "SETTLED"
    reversal["reversal_of_transaction_id"] = original["transaction_id"]
    reversal["injection_label"] = "REVERSAL_EVENT"
    bad_tx.append(reversal)
    # Mirror reversal posting in injected ledger so reversal itself is not a missing-posting issue.
    old_amt = Decimal(original["amount"])
    rev_signed = old_amt if reversal["direction"] == "CREDIT" else -old_amt
    bad_gl.append({
        "ledger_entry_id": "L-REV-" + original["transaction_id"], "transaction_id": reversal["transaction_id"],
        "account_id": reversal["account_id"], "posting_timestamp": iso(datetime.fromisoformat(reversal["event_timestamp"])+timedelta(minutes=10)),
        "signed_amount": money(rev_signed), "currency_code": reversal["currency_code"], "ledger_account": "CUSTOMER_CONTROL",
        "posting_status": "POSTED", "source_event_id": "GL-" + reversal["transaction_id"], "injection_label": "REVERSAL_EVENT"
    })
    manifest["injections"]["reversal_event"] = [reversal["transaction_id"], original["transaction_id"]]

    # 5 Invalid currency code (unsupported).
    target = next(x for x in bad_tx if not x["injection_label"])
    target["currency_code"] = "ZRX"
    target["injection_label"] = "INVALID_CURRENCY_CODE"
    manifest["injections"]["invalid_currency_code"] = [target["transaction_id"]]

    # 6 Missing ledger posting: remove one eligible posting.
    eligible = next(x for x in bad_tx if x["status"] == "SETTLED" and not x["injection_label"] and x["transaction_id"] in {g["transaction_id"] for g in bad_gl})
    bad_gl = [g for g in bad_gl if g["transaction_id"] != eligible["transaction_id"]]
    manifest["injections"]["missing_ledger_entry"] = [eligible["transaction_id"]]

    # 7 Daily spike: create a conspicuous burst of settled synthetic events on one day.
    spike_day = (start + timedelta(days=min(days-1, 5))).date()
    spike_acct = accounts[0]
    spike_ids = []
    for j in range(max(100, tx_count//30)):
        tid = f"SPIKE-{j:07d}"
        ts = datetime.combine(spike_day, datetime.min.time(), tzinfo=timezone.utc) + timedelta(minutes=j % 1440)
        amount = Decimal(rng.randint(1000, 500000))/Decimal("100")
        row = {"transaction_id": tid, "account_id": spike_acct["account_id"], "customer_id": spike_acct["customer_id"],
               "event_timestamp": iso(ts), "ingested_at": iso(ts+timedelta(minutes=2)), "transaction_type":"EFT",
               "direction":"DEBIT", "amount":money(amount), "currency_code":spike_acct["currency_code"],
               "status":"SETTLED", "reversal_of_transaction_id":"", "source_event_id":"EV-"+tid,
               "injection_label":"DAILY_VOLUME_SPIKE"}
        bad_tx.append(row); spike_ids.append(tid)
        bad_gl.append({"ledger_entry_id":"L-"+tid, "transaction_id":tid, "account_id":row["account_id"],
                       "posting_timestamp":iso(ts+timedelta(minutes=5)), "signed_amount":money(-amount),
                       "currency_code":row["currency_code"], "ledger_account":"CUSTOMER_CONTROL",
                       "posting_status":"POSTED","source_event_id":"GL-"+tid,"injection_label":"DAILY_VOLUME_SPIKE"})
    manifest["injections"]["daily_volume_spike"] = {"date": spike_day.isoformat(), "count": len(spike_ids), "sample_ids": spike_ids[:10]}

    tx_cols = list(clean_tx[0].keys())
    gl_cols = list(clean_gl[0].keys())
    write_csv(out/"customers.csv", customers, list(customers[0].keys()))
    write_csv(out/"accounts.csv", accounts, list(accounts[0].keys()))
    write_csv(out/"transactions_clean.csv", clean_tx, tx_cols)
    write_csv(out/"ledger_clean.csv", clean_gl, gl_cols)
    write_csv(out/"transactions_injected.csv", bad_tx, tx_cols)
    write_csv(out/"ledger_injected.csv", bad_gl, gl_cols)
    (out/"injection_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Generated clean transactions={len(clean_tx)}, injected transactions={len(bad_tx)}")
    print(f"Clean ledger={len(clean_gl)}, injected ledger={len(bad_gl)}")
    print(f"Output: {out.resolve()}")

if __name__ == "__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--out", default="data")
    p.add_argument("--days", type=int, default=30)
    p.add_argument("--transactions", type=int, default=100000)
    p.add_argument("--seed", type=int, default=42)
    a=p.parse_args()
    generate(Path(a.out), a.days, a.transactions, a.seed)
