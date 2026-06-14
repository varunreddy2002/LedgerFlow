"""Quick test script to verify the vLLM OCR endpoint is working.

Usage:
    python scripts/test_ocr.py
"""

import base64
import sys
import requests

VLLM_URL  = "https://bdcyudc0x0hrqy-8000.proxy.runpod.net"
MODEL     = "h2oai/h2ovl-mississippi-800m"
API_KEY   = "YOUR_RUNPOD_API_KEY"   # ← paste your RunPod API key here

HEADERS = {"Authorization": f"Bearer {API_KEY}"}


def test_models():
    """Check the model is loaded."""
    r = requests.get(f"{VLLM_URL}/v1/models", headers=HEADERS, timeout=10)
    print("Models:", r.json())


def test_text():
    """Simple text-only request — no image needed."""
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "user", "content": "Say hello in one sentence."}
        ],
        "max_tokens": 50,
    }
    r = requests.post(f"{VLLM_URL}/v1/chat/completions", headers=HEADERS, json=payload, timeout=30)
    print("Text response:", r.json()["choices"][0]["message"]["content"])


def test_image(image_path: str):
    """Send an image and ask it to extract transactions."""
    with open(image_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()

    ext = image_path.split(".")[-1].lower()
    mime = "image/png" if ext == "png" else "image/jpeg"

    payload = {
        "model": MODEL,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{mime};base64,{b64}"},
                    },
                    {
                        "type": "text",
                        "text": (
                            "Extract all transactions from this bank statement. "
                            "Return a JSON array: "
                            '[{"date": "...", "description": "...", "amount": 0.00, "type": "debit/credit"}]'
                        ),
                    },
                ],
            }
        ],
        "max_tokens": 1024,
    }

    r = requests.post(f"{VLLM_URL}/v1/chat/completions", headers=HEADERS, json=payload, timeout=60)
    print("OCR response:")
    print(r.json()["choices"][0]["message"]["content"])


if __name__ == "__main__":
    print("1. Checking model endpoint...")
    test_models()

    print("\n2. Testing text inference...")
    test_text()

    # Uncomment and pass an image path to test OCR:
    # print("\n3. Testing image OCR...")
    # test_image("path/to/bank_statement.png")
