"""Generate two fake PDFs for testing the ingestion extraction:

  kriwin_bill.pdf     -> Bill To: Kriwin   (we are the buyer  -> vendor_bill / DEBIT)
  kriwin_invoice.pdf  -> From:    Kriwin   (we are the seller -> invoice / CREDIT)

Run:  python scripts/make_fake_pdfs.py
"""

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

OUT_DIR = Path(__file__).resolve().parent
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


def main():
    _build(
        OUT_DIR / "kriwin_bill.pdf",
        title="INVOICE",
        seller="Acme Supplies LLC",
        buyer="Kriwin",
        number="ACM-1042",
        inv_date="2026-06-01",
        due_date="2026-06-30",
        items=[
            ("Cloud hosting - June", 1, 250.00),
            ("Support hours", 5, 40.00),
            ("SSL certificate", 2, 15.00),
        ],
    )

    _build(
        OUT_DIR / "kriwin_invoice.pdf",
        title="INVOICE",
        seller="Kriwin",
        buyer="Globex Inc",
        number="KRW-2025-007",
        inv_date="2026-06-10",
        due_date="2026-07-10",
        items=[
            ("Consulting - data pipeline", 12, 120.00),
            ("Onboarding setup", 1, 500.00),
        ],
    )


if __name__ == "__main__":
    main()
