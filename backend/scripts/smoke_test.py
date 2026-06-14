"""Smoke test — full CSV upload pipeline.

Steps:
  1. Creates a fake Chase CSV in memory
  2. POSTs it to /api/businesses/1/documents/upload
  3. Polls until document status = PROCESSED (or FAILED)
  4. Prints transactions + categories
  5. Rolls back / deletes everything injected

Run from the backend folder (server must be running on port 8000):
    python scripts/smoke_test.py
"""

import io
import sys
import time
import requests

BASE = "http://localhost:8000/api"
BUSINESS_ID = 1

# ---------------------------------------------------------------------------
# Fake Chase CSV
# ---------------------------------------------------------------------------
CHASE_CSV = """Transaction Date,Post Date,Description,Category,Type,Amount,Memo
01/05/2025,01/06/2025,STRIPE TRANSFER,Payment,ACH_CREDIT,2500.00,
01/07/2025,01/08/2025,AWS AMAZON WEB SERVICES,Shopping,DEBIT,-120.50,
01/10/2025,01/11/2025,GITHUB INC,Shopping,DEBIT,-10.00,
01/12/2025,01/13/2025,UBER TRIP,Travel,DEBIT,-24.75,
01/15/2025,01/16/2025,GUSTO PAYROLL,Payment,ACH_DEBIT,-1800.00,
01/18/2025,01/19/2025,GOOGLE ADS,Advertising,DEBIT,-300.00,
01/20/2025,01/21/2025,DOORDASH,Food,DEBIT,-45.00,
01/22/2025,01/23/2025,CHASE MONTHLY FEE,Fee,FEE,-15.00,
01/25/2025,01/26/2025,RANDOM VENDOR XYZ,Other,DEBIT,-200.00,
"""


def upload_csv(csv_content: str) -> dict:
    print("Uploading Chase CSV...")
    files = {"file": ("chase_test.csv", io.BytesIO(csv_content.encode()), "text/csv")}
    r = requests.post(f"{BASE}/businesses/{BUSINESS_ID}/documents/upload", files=files)
    r.raise_for_status()
    data = r.json()
    doc_id = (data.get("document") or {}).get("id")
    print(f"  document_id   = {doc_id}")
    print(f"  rows_imported = {data.get('rows_imported')}")
    print(f"  rows_skipped  = {data.get('rows_skipped')}")
    data["document_id"] = doc_id   # normalise for callers
    return data


def poll_status(document_id: int, timeout: int = 30) -> str:
    print(f"\nWaiting for categorization (document_id={document_id})...")
    for _ in range(timeout):
        r = requests.get(f"{BASE}/businesses/{BUSINESS_ID}/documents/{document_id}")
        if r.status_code == 404:
            time.sleep(1)
            continue
        status = r.json().get("status", "unknown")
        print(f"  status = {status}")
        if status in ("processed", "failed"):
            return status
        time.sleep(1)
    return "timeout"


def print_transactions(document_id: int):
    r = requests.get(
        f"{BASE}/businesses/{BUSINESS_ID}/transactions",
        params={"document_id": document_id},
    )
    if r.status_code != 200:
        print(f"  Could not fetch transactions: {r.status_code}")
        return
    txns = r.json()
    print(f"\nTransactions ({len(txns)} rows):")
    print(f"  {'Description':<35} {'Amount':>10}  {'Category':<25} {'Status'}")
    print("  " + "-" * 85)
    for t in txns:
        print(
            f"  {str(t.get('description_raw','')):<35} "
            f"{float(t.get('amount',0)):>10.2f}  "
            f"{str(t.get('category_id') or 'uncategorized'):<25} "
            f"{t.get('review_status','?')}"
        )


def cleanup(document_id: int):
    print(f"\nCleaning up document_id={document_id}...")
    # We delete via a direct DB call to keep things clean
    import os
    sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
    from app.db.database import SessionLocal
    from app.models.document import Document
    from app.models.transaction import Transaction

    db = SessionLocal()
    try:
        deleted_txns = (
            db.query(Transaction)
            .filter(Transaction.document_id == document_id)
            .delete()
        )
        deleted_docs = (
            db.query(Document).filter(Document.id == document_id).delete()
        )
        db.commit()
        print(f"  Deleted {deleted_txns} transactions + {deleted_docs} document.")
    finally:
        db.close()


def main():
    # 1. Upload
    try:
        result = upload_csv(CHASE_CSV)
    except requests.exceptions.ConnectionError:
        print("ERROR: Cannot connect to server. Is uvicorn running on port 8000?")
        sys.exit(1)
    except requests.exceptions.HTTPError as e:
        print(f"ERROR: Upload failed — {e.response.status_code}: {e.response.text}")
        sys.exit(1)

    document_id = result.get("document_id")
    if not document_id:
        print("ERROR: No document_id in response")
        sys.exit(1)

    # 2. Poll until processed
    status = poll_status(document_id)
    print(f"\nFinal status: {status}")

    # 3. Print transactions
    print_transactions(document_id)

    # 4. Cleanup
    answer = input("\nDelete test data? [y/N]: ").strip().lower()
    if answer == "y":
        cleanup(document_id)
    else:
        print("Skipped cleanup — data stays in DB.")


if __name__ == "__main__":
    main()
