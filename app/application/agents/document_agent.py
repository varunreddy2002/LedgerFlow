from langchain.agents import create_agent
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate
from app.infrastructure.llm import BedrockService, ocr_client
from app.domain.schemas import CSVColumnMapping, ExtractedDocument
import base64
import re
from pathlib import Path

from app.core.config import settings
from pydantic import BaseModel


llm_client = BedrockService(
    settings.default_chat_model,
    model_kwargs={"temperature": 0, "max_tokens": 4000}
    )


def map_columns(headers: list, data_chunk: list) -> CSVColumnMapping:
    prompt = "You are a financial data mapping assistant. Map the CSV columns to the required fields. If you cannot confidently map a field set it to null."
    message = f"Headers: {headers}\nSample rows: {data_chunk}"

    return llm_client.invoke_structured(message, prompt, CSVColumnMapping)

_EXTRACTION_PROMPT = """You are a financial document extraction assistant.
You will be given an invoice or a bill as a PDF.
Extract the data exactly as it appears on the document. Do not guess or calculate.
Use null for any field that is not visible on the document.
Dates must be in YYYY-MM-DD format.
For each line item, extract its description, quantity, net price (per unit, before tax), and tax amount if shown."""


def extract_document(pdf_bytes: bytes, business_name: str, filename: str) -> ExtractedDocument:
    pdf_b64 = base64.b64encode(pdf_bytes).decode("utf-8")

    model = ocr_client.with_structured_output(ExtractedDocument)
    doc_name = _clean_doc_name(filename)
    messages = [
        SystemMessage(content=_EXTRACTION_PROMPT),
        HumanMessage(content=[
            {"type": "text", "text": "Extract all the data from this document."},
            {
                "type": "file",
                "source_type": "base64",
                "name": doc_name,
                "mime_type": "application/pdf",
                "data": pdf_b64,
            },
        ]),
    ]

    return model.invoke(messages)


def _clean_doc_name(filename: str) -> str:
    stem = Path(filename).stem                              # drop ".pdf"
    cleaned = re.sub(r"[^A-Za-z0-9 ()\[\]-]", " ", stem)    # replace illegal chars with space
    cleaned = re.sub(r"\s+", " ", cleaned).strip()          # collapse multiple spaces
    return cleaned or "document"                