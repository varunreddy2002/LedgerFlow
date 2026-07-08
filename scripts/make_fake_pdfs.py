"""Generate fake PDFs for testing the ingestion extraction.

  bill_*     -> Bill To: Kriwin   (we are the buyer  -> vendor_bill / PAYABLE)
  invoice_*  -> From:    Kriwin   (we are the seller -> invoice / RECEIVABLE)

Files are written to  <project-root>/sample_docs/

Run:  python scripts/make_fake_pdfs.py
"""

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

OUT_DIR = Path(__file__).resolve().parent.parent / "sample_docs"
OUT_DIR.mkdir(exist_ok=True)
styles = getSampleStyleSheet()


def _money(v: float) -> str:
    return f"${v:,.2f}"


def _build(path: Path, *, title, seller, buyer, number, inv_date, due_date, items, tax_rate=0.10):
    """items: list of (description, qty, unit_price)"""
    doc = SimpleDocTemplate(str(path), pagesize=A4)
    story = []

    story.append(Paragraph(title, styles["Title"]))
    story.append(Spacer(1, 12))

    story.append(Paragraph(f"<b>From:</b> {seller}", styles["Normal"]))
    story.append(Paragraph(f"<b>Bill To:</b> {buyer}", styles["Normal"]))
    story.append(Spacer(1, 8))
    story.append(Paragraph(f"<b>Invoice Number:</b> {number}", styles["Normal"]))
    story.append(Paragraph(f"<b>Invoice Date:</b> {inv_date}", styles["Normal"]))
    story.append(Paragraph(f"<b>Due Date:</b> {due_date}", styles["Normal"]))
    story.append(Spacer(1, 16))

    rows = [["Description", "Qty", "Unit Price", "Line Total"]]
    subtotal = 0.0
    for desc, qty, unit in items:
        line = qty * unit
        subtotal += line
        rows.append([desc, str(qty), _money(unit), _money(line)])

    tax = round(subtotal * tax_rate, 2)
    total = round(subtotal + tax, 2)

    rows.append(["", "", "Subtotal", _money(subtotal)])
    rows.append(["", "", f"Tax ({int(tax_rate*100)}%)", _money(tax)])
    rows.append(["", "", "Total", _money(total)])

    table = Table(rows, colWidths=[230, 50, 90, 90])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#333333")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -4), 0.5, colors.grey),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME", (2, -1), (-1, -1), "Helvetica-Bold"),
    ]))
    story.append(table)

    doc.build(story)
    print(f"wrote {path.name}  (subtotal={subtotal}, tax={tax}, total={total})")


# --- Vendor bills (Kriwin is the buyer -> PAYABLE) --------------------------
BILLS = [
    dict(
        filename="bill_acme_supplies.pdf",
        seller="Acme Supplies LLC", number="ACM-1042",
        inv_date="2026-06-01", due_date="2026-06-30",
        items=[
            ("Cloud hosting - June", 1, 250.00),
            ("Support hours", 5, 40.00),
            ("SSL certificate", 2, 15.00),
        ],
    ),
    dict(
        filename="bill_aws.pdf",
        seller="Amazon Web Services", number="AWS-2026-06-8891",
        inv_date="2026-06-01", due_date="2026-06-15",
        items=[
            ("EC2 compute - June", 1, 342.55),
            ("S3 storage", 1, 87.20),
            ("Data transfer", 1, 45.10),
        ],
    ),
    dict(
        filename="bill_stripe_fees.pdf",
        seller="Stripe Inc", number="STR-JUN-2026-4412",
        inv_date="2026-06-30", due_date="2026-06-30",
        items=[
            ("Payment processing fees - June", 1, 612.40),
            ("Dispute resolution fees", 3, 15.00),
        ],
    ),
    dict(
        filename="bill_github_enterprise.pdf",
        seller="GitHub Inc", number="GH-INV-88231",
        inv_date="2026-05-28", due_date="2026-06-27",
        items=[
            ("GitHub Enterprise seats", 8, 21.00),
            ("Advanced Security add-on", 8, 49.00),
        ],
    ),
    dict(
        filename="bill_notion.pdf",
        seller="Notion Labs Inc", number="NTN-72-1049",
        inv_date="2026-06-05", due_date="2026-07-05",
        items=[
            ("Business plan seats", 12, 18.00),
        ],
    ),
    dict(
        filename="bill_fedex_shipping.pdf",
        seller="FedEx Corporation", number="FDX-2026-06-3311",
        inv_date="2026-06-18", due_date="2026-07-18",
        items=[
            ("Overnight shipping - client kits", 6, 42.50),
            ("Ground shipping - equipment return", 2, 18.75),
        ],
    ),
    dict(
        filename="bill_adobe_creative.pdf",
        seller="Adobe Inc", number="ADB-92014-06",
        inv_date="2026-06-08", due_date="2026-07-08",
        items=[
            ("Creative Cloud - team license", 4, 54.99),
        ],
    ),
    dict(
        filename="bill_uber_business.pdf",
        seller="Uber Technologies", number="UBR-JUN26-1188",
        inv_date="2026-06-30", due_date="2026-07-15",
        items=[
            ("Client meeting rides", 14, 22.10),
            ("Airport transfers", 3, 45.00),
        ],
    ),
]

# --- Invoices (Kriwin is the seller -> RECEIVABLE) --------------------------
INVOICES = [
    dict(
        filename="invoice_globex.pdf",
        buyer="Globex Inc", number="KRW-2025-007",
        inv_date="2026-06-10", due_date="2026-07-10",
        items=[
            ("Consulting - data pipeline", 12, 120.00),
            ("Onboarding setup", 1, 500.00),
        ],
    ),
    dict(
        filename="invoice_umbrella_corp.pdf",
        buyer="Umbrella Corporation", number="KRW-2026-012",
        inv_date="2026-06-15", due_date="2026-07-15",
        items=[
            ("Custom platform development", 40, 175.00),
            ("Design review sessions", 4, 200.00),
        ],
    ),
    dict(
        filename="invoice_wayne_enterprises.pdf",
        buyer="Wayne Enterprises", number="KRW-2026-013",
        inv_date="2026-06-20", due_date="2026-07-20",
        items=[
            ("ETL pipeline build", 60, 150.00),
            ("Monthly monitoring retainer", 1, 1500.00),
        ],
    ),
    dict(
        filename="invoice_stark_industries.pdf",
        buyer="Stark Industries", number="KRW-2026-014",
        inv_date="2026-06-22", due_date="2026-07-22",
        items=[
            ("Analytics dashboard - Q2 build", 25, 160.00),
            ("Executive training", 2, 800.00),
        ],
    ),
    dict(
        filename="invoice_nakatomi_trading.pdf",
        buyer="Nakatomi Trading Co", number="KRW-2026-015",
        inv_date="2026-06-25", due_date="2026-07-25",
        items=[
            ("Legacy system integration", 30, 140.00),
            ("QA test suite", 15, 90.00),
        ],
    ),
]


def main():
    for b in BILLS:
        _build(
            OUT_DIR / b["filename"],
            title="INVOICE",
            seller=b["seller"], buyer="Kriwin",
            number=b["number"], inv_date=b["inv_date"], due_date=b["due_date"],
            items=b["items"],
        )
    for i in INVOICES:
        _build(
            OUT_DIR / i["filename"],
            title="INVOICE",
            seller="Kriwin", buyer=i["buyer"],
            number=i["number"], inv_date=i["inv_date"], due_date=i["due_date"],
            items=i["items"],
        )


if __name__ == "__main__":
    main()
