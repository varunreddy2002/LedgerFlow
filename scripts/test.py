import base64
import json
import re

import fitz
import requests



VLLM_URL = "http://ec2-3-239-98-191.compute-1.amazonaws.com:8000"
VLLM_KEY  = "sk-zs7wv74zphqchq"
MODEL     = "h2oai/h2ovl-mississippi-800m"
#DOC_PATH  = r"C:\Users\varun\Downloads\invoice_101_charspace_102.pdf"
#DOC_PATH = r"C:\Users\varun\Downloads\1000+ PDF_Invoice_Folder\1000+ PDF_Invoice_Folder\invoice_Theone Pippenger_23252.pdf"
#DOC_PATH = r"C:\Users\varun\Downloads\1000+ PDF_Invoice_Folder\1000+ PDF_Invoice_Folder\invoice_Theresa Swint_21236.pdf"
#DOC_PATH = r"C:\Users\varun\Downloads\1000+ PDF_Invoice_Folder\1000+ PDF_Invoice_Folder\invoice_Ralph Arnett_17190.pdf"
DOC_PATH = r"C:\Users\varun\Downloads\1000+ PDF_Invoice_Folder\1000+ PDF_Invoice_Folder\invoice_Tracy Blumstein_20584.pdf"

PASS1_PROMPT = """
Extract invoice data from the image.

Return JSON only.
Do not explain.
Do not add extra keys.
Do not guess.
Use null if a value is not visible.

Extract:

* vendor_name
* invoice_number
* invoice_date in YYYY-MM-DD format

For each line item, extract only:

* description: item name
* quantity: quantity of the item
* net_price: price per single unit before tax

Return exactly this format:

{
"vendor_name": null,
"invoice_number": null,
"invoice_date": null,
"line_items": [
{
"description": null,
"quantity": null,
"net_price": null
}
]
}

"""

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
        "max_tokens": 2048,
        "temperature": 0.0,
    }
    r = requests.post(f"{VLLM_URL}/v1/chat/completions", json=payload, timeout=120)
    if not r.ok:
        print(f"  ERROR {r.status_code}: {r.text}")
        r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"].strip()


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

        t= _call_model(img_b64, PASS1_PROMPT)
        print(t)


if __name__ == "__main__":
    main()