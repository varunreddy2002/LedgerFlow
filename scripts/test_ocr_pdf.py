"""Quick OCR test — 2-pass technique for h2oai/h2ovl-mississippi-800m.

Pass 1: discover the exact table column headers from the image.
Pass 2: use those headers (with an explicit key mapping) to extract invoice data.

Usage:
    python scripts/test_ocr_pdf.py
"""

import base64
import json
import re

import fitz
import requests

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
VLLM_URL = "https://zs7wv74zphqchq-8000.proxy.runpod.net"
VLLM_KEY  = "sk-zs7wv74zphqchq"
MODEL     = "h2oai/h2ovl-mississippi-800m"
DOC_PATH  = r"C:\Users\varun\Downloads\invoice_101_charspace_102.pdf"
#DOC_PATH = r"C:\Users\varun\Downloads\invoice_9caf94ce_3.pdf"
# ---------------------------------------------------------------------------

HEADERS_HTTP = {"Authorization": f"Bearer {VLLM_KEY}"}

# ---------------------------------------------------------------------------
# Heuristic mapper: discovered header → schema key
# Add more synonyms as you encounter new vendors.
# ---------------------------------------------------------------------------
_HEADER_SYNONYMS: dict[str, str] = {
    # description
    "description": "description",
    "item description": "description",
    "item": "description",
    "particulars": "description",
    "product": "description",
    "service": "description",
    "details": "description",
    "narration": "description",
    # quantity
    "qty": "quantity",
    "quantity": "quantity",
    "units": "quantity",
    "no": "quantity",
    "nos": "quantity",
    "pcs": "quantity",
    "count": "quantity",
    # unit
    "unit": "unit",
    "uom": "unit",
    "measure": "unit",
    # unit_price
    "rate": "unit_price",
    "unit price": "unit_price",
    "price": "unit_price",
    "unit rate": "unit_price",
    "mrp": "unit_price",
    "cost": "unit_price",
    # amount
    "amount": "amount",
    "total": "amount",
    "line total": "amount",
    "net amount": "amount",
    "value": "amount",
    "subtotal": "amount",
    "sub total": "amount",
}

# ---------------------------------------------------------------------------
# Pass 1 prompt
# ---------------------------------------------------------------------------
PASS1_PROMPT = """\
You are an expert OCR document processor. Analyze the invoice table on this page.
Identify the exact text used in the table header row.
Output ONLY a JSON array of the literal header strings found, from left to right.
Do not rename them.
["\
"""

# ---------------------------------------------------------------------------
# Pass 2 prompt template
# ---------------------------------------------------------------------------
PASS2_TEMPLATE = """\
This is an invoice page. Extract the following fields and output ONLY raw JSON.

Scalar fields:
- vendor_name: the seller or company name
- invoice_number: the invoice ID (labeled Invoice #, Invoice No, Inv No, etc.)
- invoice_date: date the invoice was issued, format YYYY-MM-DD
- due_date: payment due date, format YYYY-MM-DD (omit if not shown)
- total_amount: the final payable total (labeled Total, Grand Total, Amount Due, etc.)

Line items table — the columns in this invoice map to these keys:
{column_mapping}

Extract EVERY row from the table as an array called line_items.
Omit a field if it is not visible. Do not invent values.

{{\
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def page_to_base64(doc_path: str, page_num: int = 0) -> str:
    doc = fitz.open(doc_path)
    page = doc[page_num]
    mat = fitz.Matrix(2.0, 2.0)
    pix = page.get_pixmap(matrix=mat)
    img_bytes = pix.tobytes("png")
    doc.close()
    return base64.b64encode(img_bytes).decode()


def _call_model(image_b64: str, prompt: str) -> str:
    payload = {
        "model": MODEL,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_b64}"}},
                {"type": "text", "text": prompt},
            ],
        }],
        "max_tokens": 512,
        "temperature": 0.0,
    }
    r = requests.post(f"{VLLM_URL}/v1/chat/completions", headers=HEADERS_HTTP, json=payload, timeout=120)
    if not r.ok:
        print(f"  ERROR {r.status_code}: {r.text}")
        r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"].strip()


def _clean_array(raw: str) -> list[str]:
    """Best-effort extraction of a JSON array from model output."""
    raw = re.sub(r"```(?:json)?", "", raw).strip()
    if not raw.startswith("["):
        raw = '["' + raw
    start, end = raw.find("["), raw.rfind("]")
    if start != -1 and end != -1:
        raw = raw[start:end + 1]
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return []


def _clean_object(raw: str) -> dict:
    """Best-effort extraction of a JSON object from model output."""
    raw = re.sub(r"```(?:json)?", "", raw).strip()
    if not raw.startswith("{"):
        raw = "{" + raw
    start, end = raw.find("{"), raw.rfind("}")
    if start != -1 and end != -1:
        raw = raw[start:end + 1]
    return json.loads(raw)


def map_headers(headers: list[str]) -> dict[str, str]:
    """Map discovered header strings to schema keys using synonym lookup."""
    mapping = {}
    for h in headers:
        key = _HEADER_SYNONYMS.get(h.strip().lower())
        if key:
            mapping[h] = key
    return mapping


def build_column_mapping_text(header_to_key: dict[str, str]) -> str:
    """Build the explicit mapping block injected into pass 2 prompt."""
    if not header_to_key:
        return '  (no table headers detected — extract line items by best guess)'
    lines = []
    for header, key in header_to_key.items():
        lines.append(f'  column "{header}" → {key}')
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Two-pass extraction
# ---------------------------------------------------------------------------

def pass1_discover_headers(image_b64: str) -> list[str]:
    print("  [Pass 1] Discovering table headers...")
    raw = _call_model(image_b64, PASS1_PROMPT)
    print(f"  [Pass 1] Raw output: {raw!r}")
    headers = _clean_array(raw)
    print(f"  [Pass 1] Parsed headers: {headers}")
    return headers


def pass2_extract(image_b64: str, header_to_key: dict[str, str]) -> dict:
    column_mapping = build_column_mapping_text(header_to_key)
    prompt = PASS2_TEMPLATE.format(column_mapping=column_mapping)
    print(f"  [Pass 2] Extracting with mapping:\n{column_mapping}")
    raw = _call_model(image_b64, prompt)
    print(f"  [Pass 2] Raw output:\n{raw}")
    return _clean_object(raw)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    doc = fitz.open(DOC_PATH)
    total_pages = len(doc)
    doc.close()
    print(f"Document : {DOC_PATH}")
    print(f"Model    : {MODEL}")
    print(f"Pages    : {total_pages}\n")

    for i in range(total_pages):
        print(f"{'=' * 50}")
        print(f"Page {i + 1} of {total_pages}")
        print(f"{'=' * 50}")

        img_b64 = page_to_base64(DOC_PATH, i)

        # Pass 1 — layout discovery
        headers = pass1_discover_headers(img_b64)
        header_to_key = map_headers(headers)

        unmapped = [h for h in headers if h not in header_to_key]
        if unmapped:
            print(f"  [Pass 1] Unmapped headers (add to _HEADER_SYNONYMS): {unmapped}")

        # Pass 2 — data extraction
        try:
            result = pass2_extract(img_b64, header_to_key)
            print("\n  [Result]")
            print(json.dumps(result, indent=2))
        except json.JSONDecodeError as e:
            print(f"  [Pass 2] Invalid JSON: {e}")

        print()


if __name__ == "__main__":
    main()
