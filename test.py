from pathlib import Path
from app.application.services.ingestion_service import run_ingestion

for name in ["kriwin_bill.pdf", "kriwin_invoice.pdf"]:
    content = Path("scripts") / name
    run_ingestion(business_id=1, filename=name, content=content.read_bytes(), ext=".pdf")

"""


content = Path("scripts/kriwin_bank_statement.csv").read_bytes()
run_ingestion(business_id=1, filename="kriwin_bank_statement.csv", content=content, ext=".csv")

"""