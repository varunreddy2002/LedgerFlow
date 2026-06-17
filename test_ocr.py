"""
Smoke test: uv run python test_ocr.py path/to/invoice.pdf
"""

import sys
import httpx
from app.core.config import settings
from app.services.ocr_service import OCRService

INVOICE_SCHEMA = {
    "vendor_name":    {"type": "string",     "hint": "Seller or company name who issued the invoice"},
    "invoice_number": {"type": "string",     "hint": "Invoice ID or reference, labeled Invoice #, Inv No, Bill No"},
    "invoice_date":   {"type": "date",       "hint": "Date the invoice was issued, output as YYYY-MM-DD"},
    "due_date":       {"type": "date|null",  "hint": "Payment due date, output as YYYY-MM-DD. Omit if not shown"},
    "total_amount":   {"type": "float",      "hint": "Grand total (may be labeled Total, Gross worth, Amount due, Grand total)"},
    "line_items": {
        "type": "array",
        "hint": "Every product or service row — exclude tax rows",
        "item_schema": {
            "description": "string",
            "quantity":    "number",
            "unit":        "string",
            "unit_price":  "float",
            "amount":      "float",
        },
    },
}


def check_config():
    print(f"  vllm_base_url : {settings.vllm_base_url!r}")
    print(f"  vllm_api_key  : {settings.vllm_api_key[:6]}..." if settings.vllm_api_key else "  vllm_api_key  : (empty!)")
    print(f"  ocr_model     : {settings.ocr_model!r}")
    if not settings.vllm_base_url:
        print("ERROR: vllm_base_url is empty — check your .env file.")
        sys.exit(1)


def check_connectivity():
    base = settings.vllm_base_url.rstrip("/")
    headers = {"Authorization": f"Bearer {settings.vllm_api_key}"}
    try:
        r = httpx.get(f"{base}/v1/models", headers=headers, timeout=15)
        if r.status_code == 200:
            models = [m["id"] for m in r.json().get("data", [])]
            print(f"  ✓ Connected — models: {models}")
        elif r.status_code == 401:
            print("  ✗ 401 Unauthorized — API key is wrong")
            sys.exit(1)
        else:
            print(f"  ✗ Unexpected {r.status_code}: {r.text[:200]}")
            sys.exit(1)
    except httpx.ConnectError as e:
        print(f"  ✗ Connection failed: {e}")
        sys.exit(1)


def run_extraction(pdf_path: str):
    svc = OCRService()
    result = svc.ocr_extract(pdf_path, INVOICE_SCHEMA)
    print("\n  ✓ Extraction complete\n")
    for field, value in result.items():
        if isinstance(value, list):
            print(f"  {field}:")
            for item in value:
                print(f"    {item}")
        else:
            print(f"  {field}: {value}")


if __name__ == "__main__":
    print("=== Config ===")
    check_config()

    #print("\n=== Connectivity ===")
    #check_connectivity()

    if len(sys.argv) < 2:
        print("\nPass a PDF path to test extraction.")
        sys.exit(0)

    print(f"\n=== OCR: {sys.argv[1]} ===")
    try:
        run_extraction(sys.argv[1])
    except Exception as e:
        import traceback
        print(f"  ✗ {e}")
        traceback.print_exc()
        sys.exit(1)
