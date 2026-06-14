"""Quick OCR test — sends a PDF to the vLLM endpoint and prints the response.

Usage:
    pip install PyMuPDF requests
    python scripts/test_ocr_pdf.py
"""

import base64
import sys
import requests
import fitz  # PyMuPDF

# ---------------------------------------------------------------------------
# Config — fill these in
# ---------------------------------------------------------------------------
VLLM_URL  = "https://4efjrzpydo2b8j-8000.proxy.runpod.net"
VLLM_KEY  = "sk-4efjrzpydo2b8j"   # ← paste the value of $VLLM_API_KEY from pod terminal
MODEL     = "h2oai/h2ovl-mississippi-800m"
PDF_PATH  = r"C:\Users\varun\Downloads\invoice_101_charspace_102.pdf"
# ---------------------------------------------------------------------------

HEADERS = {"Authorization": f"Bearer {VLLM_KEY}"}

PROMPT = (
    "Extract all data from this invoice. "
    "Output ONLY a raw JSON object. "
    "No markdown, no code blocks, no backticks, no explanation. "
    "Start your response with { and end with }. "
    "Fields: invoice_number, invoice_date, due_date, "
    "vendor (name, address, email, phone), "
    "client (name, address), "
    "line_items (array of: description, quantity, unit_price, amount), "
    "subtotal, tax, total, currency. "
    "Read the ACTUAL numbers from the document — do not use 0.00 as a placeholder. "
    "Extract every single line item without skipping any."
)


def pdf_page_to_base64(pdf_path: str, page_num: int = 0) -> str:
    """Convert a PDF page to a base64-encoded PNG."""
    doc = fitz.open(pdf_path)
    page = doc[page_num]
    # Render at 1x resolution to keep image tokens within model context
    mat = fitz.Matrix(1.0, 1.0)
    pix = page.get_pixmap(matrix=mat)
    img_bytes = pix.tobytes("png")
    doc.close()
    return base64.b64encode(img_bytes).decode()


def clean_json(raw: str) -> str:
    """Strip markdown code fences and return only the JSON part."""
    import re
    # Remove ```json ... ``` or ``` ... ```
    raw = re.sub(r"```(?:json)?", "", raw).strip()
    # Find the first { and last } and extract only that
    start = raw.find("{")
    end = raw.rfind("}")
    if start != -1 and end != -1:
        return raw[start:end + 1]
    return raw


def ask_model(image_b64: str, page_num: int) -> str:
    payload = {
        "model": MODEL,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{image_b64}"},
                    },
                    {
                        "type": "text",
                        "text": PROMPT,
                    },
                ],
            }
        ],
        "max_tokens": 1500,
        "temperature": 0.0,
    }

    print(f"  Sending page {page_num + 1} to model...")
    r = requests.post(
        f"{VLLM_URL}/v1/chat/completions",
        headers=HEADERS,
        json=payload,
        timeout=120,
    )
    if not r.ok:
        print(f"  ERROR {r.status_code}: {r.text}")
        r.raise_for_status()
    raw = r.json()["choices"][0]["message"]["content"]
    return clean_json(raw)


def main():
    # Count pages
    doc = fitz.open(PDF_PATH)
    total_pages = len(doc)
    doc.close()
    print(f"PDF: {PDF_PATH}")
    print(f"Pages: {total_pages}\n")

    for i in range(total_pages):
        print(f"--- Page {i + 1} ---")
        img_b64 = pdf_page_to_base64(PDF_PATH, i)
        result = ask_model(img_b64, i)
        try:
            import json
            parsed = json.loads(result)
            print(json.dumps(parsed, indent=2))
        except json.JSONDecodeError:
            print("RAW (not valid JSON):")
            print(result)
        print()


if __name__ == "__main__":
    if "YOUR_VLLM_API_KEY" in VLLM_KEY:
        print("ERROR: Set your VLLM_API_KEY in the script first.")
        sys.exit(1)
    main()
