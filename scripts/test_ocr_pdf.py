"""PDF full-content extraction test — h2oai/h2ovl-mississippi models.

Processes a PDF page by page, sends each page as an image to the configured
vLLM endpoint, and captures the raw model output.

Results are saved to outputs/<model_label>_<timestamp>.json

Usage:
    python scripts/test_ocr_pdf.py
"""

import base64
import json
import os
import time
from datetime import datetime

import fitz
import requests

# ---------------------------------------------------------------------------
# Config — change MODEL + VLLM_URL when switching between 800m and 2b
# ---------------------------------------------------------------------------
VLLM_URL = "http://ec2-3-83-32-175.compute-1.amazonaws.com:8000"
MODEL     = "h2oai/h2ovl-mississippi-2b"
DOC_PATH  = r"C:\Users\varun\Downloads\Pup Jt - PO.pdf"
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "output")

# ---------------------------------------------------------------------------
# Extraction prompt
# ---------------------------------------------------------------------------
PROMPT = """\
You are an OCR information extraction engine.

Extract structured information from this purchase order document image.

The page layout is known:

* Top left: company logo. Ignore the logo.
* Top right: barcode with a reference number.
* Main information table: two-column table where field labels are on the left and values are on the right.
* Supplier and Purchaser section: two columns below the main table.

  * Left column contains Supplier information.
  * Right column contains Purchaser information.
* Bottom section contains Requestor contact details.

Important extraction rules:

1. Extract only text that is visibly present in the document.
2. Do not guess missing values.
3. If a field is not found or unreadable, return null.
4. Preserve the original spelling, capitalization, currency symbols, commas, decimals, dates, email addresses, and phone numbers.
5. Do not mix Supplier and Purchaser details.
6. For addresses, combine multiline address text into one string, preserving the order.
7. Return valid JSON only.
8. Do not include explanation, markdown, comments, or extra text.

Extract the following fields:

{
"barcode_reference_number": null,
"order_details": {
"status": null,
"purchase_order_number": null,
"purchasing_organization": null,
"purchasing_group": null,
"division": null,
"plant": null,
"company_code": null,
"business_unit": null,
"bu_company_code": null
},
"financial_timeline": {
"payment_terms": null,
"order_submitted_date": null,
"supplier_acknowledged_date": null,
"net_total": null,
"tax": null,
"gross_total": null
},
"supplier": {
"company_name": null,
"supplier_id": null,
"address": null,
"email": null,
"phone": null
},
"purchaser": {
"company_name": null,
"address": null
},
"requestor": {
"name": null,
"email": null,
"phone": null
}
}

"""

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def page_to_base64(doc_path: str, page_num: int) -> str:
    doc = fitz.open(doc_path)
    page = doc[page_num]
    pix = page.get_pixmap(matrix=fitz.Matrix(2.0, 2.0))
    img_bytes = pix.tobytes("png")
    doc.close()
    return base64.b64encode(img_bytes).decode()


def call_model(image_b64: str) -> str:
    payload = {
        "model": MODEL,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_b64}"}},
                {"type": "text", "text": PROMPT},
            ],
        }],
        "max_tokens": 2048,
        "temperature": 0.0,
    }
    r = requests.post(
        f"{VLLM_URL}/v1/chat/completions",
        json=payload,
        timeout=180,
    )
    if not r.ok:
        raise RuntimeError(f"HTTP {r.status_code}: {r.text}")
    return r.json()["choices"][0]["message"]["content"].strip()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    doc = fitz.open(DOC_PATH)
    total_pages = 1
    doc.close()

    model_label = MODEL.split("/")[-1]
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    print(f"Document : {DOC_PATH}")
    print(f"Model    : {MODEL}")
    print(f"Pages    : {total_pages}")
    print(f"Output   : {OUTPUT_DIR}")
    print()

    results = {
        "model": MODEL,
        "doc_path": DOC_PATH,
        "timestamp": timestamp,
        "total_pages": total_pages,
        "pages": [],
    }

    for i in range(total_pages):
        print(f"{'=' * 60}")
        print(f"Page {i + 1} / {total_pages}")
        print(f"{'=' * 60}")

        img_b64 = page_to_base64(DOC_PATH, i)

        start = time.time()
        try:
            raw_output = call_model(img_b64)
            elapsed = round(time.time() - start, 2)
            status = "ok"
        except Exception as e:
            raw_output = f"ERROR: {e}"
            elapsed = round(time.time() - start, 2)
            status = "error"

        page_result = {
            "page": i + 1,
            "status": status,
            "elapsed_seconds": elapsed,
            "raw_output": raw_output,
        }
        results["pages"].append(page_result)

        print(f"  Status  : {status}")
        print(f"  Elapsed : {elapsed}s")
        print(f"  Output  :\n{raw_output}")
        print()

    # Save to file
    out_file = os.path.join(OUTPUT_DIR, f"{model_label}_{timestamp}.json")
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    # Final summary
    print(f"{'=' * 60}")
    print("SUMMARY")
    print(f"{'=' * 60}")
    for p in results["pages"]:
        print(f"  Page {p['page']:>2} — {p['status']} — {p['elapsed_seconds']}s")
    print()
    print(f"Results saved to: {out_file}")


if __name__ == "__main__":
    main()
