import base64
import json
import re
from datetime import datetime

import fitz
from openai import OpenAI

from app.core.config import settings

_DATE_KEYS = {"invoice_date", "due_date", "date"}
_DATE_FORMATS = ["%m/%d/%Y", "%d/%m/%Y", "%d-%m-%Y", "%m-%d-%Y", "%B %d, %Y", "%b %d, %Y", "%d %B %Y"]


def _normalize_number(value) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        cleaned = re.sub(r'[^\d,.]', '', value.strip())
        if not cleaned:
            return None
        if ',' in cleaned and '.' not in cleaned:
            # European decimal: "54,95" → 54.95
            cleaned = cleaned.replace(',', '.')
        elif ',' in cleaned and '.' in cleaned:
            if cleaned.rindex(',') > cleaned.rindex('.'):
                # European thousands + decimal: "1.234,56" → 1234.56
                cleaned = cleaned.replace('.', '').replace(',', '.')
            else:
                # US thousands: "1,234.56" → 1234.56
                cleaned = cleaned.replace(',', '')
        try:
            return float(cleaned)
        except ValueError:
            return None
    return None


def _normalize_date(value: str | None) -> str | None:
    if not value or not isinstance(value, str):
        return value
    if re.match(r"^\d{4}-\d{2}-\d{2}$", value):
        return value
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(value.strip(), fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return value


_BASE_PROMPT = """\
Extract data from this invoice page.
Output ONLY a raw JSON object. No markdown, no code blocks, no explanation. Start with {{ and end with }}.

Fields: {schema}

Rules:
- Read the ACTUAL numbers from the document — do not use 0.00 as a placeholder.
- Extract every single line item without skipping any. Join multi-line descriptions into one string.
- Dates: output as YYYY-MM-DD.
- Omit a field entirely if it is not visible on this page — do not guess.
- If you see a Tax / GST / VAT row, put its amount in tax_amount — do not include it as a line item.
"""


class OCRService:
    def __init__(self):
        self.client = OpenAI(
            base_url=f"{settings.vllm_base_url.rstrip('/')}/v1",
            api_key=settings.vllm_api_key,
        )
        self.model = settings.ocr_model

    def _pdf_to_images(self, file_path: str) -> list[str]:
        doc = fitz.open(file_path)
        images = []
        mat = fitz.Matrix(2.0, 2.0)
        for page in doc:
            pix = page.get_pixmap(matrix=mat)
            images.append(base64.b64encode(pix.tobytes("png")).decode())
        doc.close()
        return images

    @staticmethod
    def _build_accumulator(schema: dict) -> dict:
        return {
            key: [] if field["type"] == "array" else None
            for key, field in schema.items()
        }

    @staticmethod
    def _missing_fields(schema: dict, accumulator: dict) -> list[str]:
        return [
            key for key, field in schema.items()
            if field["type"] == "array" or accumulator[key] is None
        ]

    @staticmethod
    def _build_schema_snippet(schema: dict, fields: list[str]) -> str:
        parts = []
        for key in fields:
            field = schema[key]
            if "item_schema" in field:
                sub = ", ".join(field["item_schema"].keys())
                parts.append(f"{key} (array of: {sub})")
            else:
                parts.append(f"{key} ({field['hint']})")
        return ", ".join(parts)

    def _build_prompt(self, schema: dict, missing: list[str]) -> str:
        return _BASE_PROMPT.format(schema=self._build_schema_snippet(schema, missing))

    @staticmethod
    def _clean_json(raw: str) -> str:
        raw = re.sub(r"```(?:json)?", "", raw).strip()
        start, end = raw.find("{"), raw.rfind("}")
        if start != -1 and end != -1:
            return raw[start:end + 1]
        return raw

    @staticmethod
    def _normalize_accumulator(schema: dict, accumulator: dict) -> dict:
        for key, field in schema.items():
            if "float" in field["type"] and accumulator[key] is not None:
                accumulator[key] = _normalize_number(accumulator[key])

            elif field["type"] == "array":
                item_schema = field.get("item_schema", {})
                if not item_schema:
                    continue
                cleaned = []
                for item in accumulator[key]:
                    clean = {}
                    for item_key, item_type in item_schema.items():
                        if item_key in item:
                            val = item[item_key]
                        elif item_key == "description":
                            # model split description across type + description — reconstruct
                            parts = [item.get("type", ""), item.get("description", "")]
                            val = " ".join(p.strip() for p in parts if p).strip() or None
                        else:
                            val = None

                        if val is not None and item_type in ("float", "number"):
                            val = _normalize_number(val)
                        clean[item_key] = val

                    # correct quantity when European comma caused 5,00 → 500
                    qty = clean.get("quantity")
                    price = clean.get("unit_price")
                    amt = clean.get("amount")
                    if qty and price and amt and amt > 0:
                        if abs(qty * price - amt) / amt > 0.1:
                            corrected = qty / 100
                            if abs(corrected * price - amt) / amt < 0.05:
                                clean["quantity"] = corrected

                    cleaned.append(clean)
                accumulator[key] = cleaned
        return accumulator

    @staticmethod
    def _merge(accumulator: dict, new_values: dict) -> dict:
        for key, new_val in new_values.items():
            if key not in accumulator:
                continue
            current = accumulator[key]
            if isinstance(current, list):
                accumulator[key] = current + (new_val if isinstance(new_val, list) else [])
            elif current is None and new_val is not None:
                if key in _DATE_KEYS:
                    new_val = _normalize_date(new_val)
                accumulator[key] = new_val
        return accumulator

    def ocr_extract(self, file_path: str, schema: dict) -> dict:
        images = self._pdf_to_images(file_path)
        accumulator = self._build_accumulator(schema)

        for page_num, img_data in enumerate(images, 1):
            missing = self._missing_fields(schema, accumulator)
            print(f"  Page {page_num}/{len(images)} — extracting: {', '.join(missing)}")

            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": self._build_prompt(schema, missing)},
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_data}"}},
                    ],
                }],
                max_tokens=2048,
                temperature=0.0,
            )
            cleaned = self._clean_json(response.choices[0].message.content)
            try:
                new_values = json.loads(cleaned)
                accumulator = self._merge(accumulator, new_values)
                accumulator = self._normalize_accumulator(schema, accumulator)
            except json.JSONDecodeError as e:
                print(f"  Warning: page {page_num} returned invalid JSON — skipping. ({e})")

        return accumulator
