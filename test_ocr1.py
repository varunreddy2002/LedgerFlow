from langchain_openai import ChatOpenAI
from sqlalchemy import Extract
from langchain_core.messages import SystemMessage, HumanMessage, ChatMessage
llm = ChatOpenAI(model="h2oai/h2ovl-mississippi-800m",
                 base_url="https://c4rf9kkr722h8q-8000.proxy.runpod.net",
                 api_key="sk-c4rf9kkr722h8q",
                 max_tokens=2048)

import fitz
import base64

pdf_path = r"C:\Users\varun\Downloads\invoice_101_charspace_102.pdf"
doc = fitz.open(pdf_path)
mat = fitz.Matrix(1.0, 1.0)
page = doc[0]
pix = page.get_pixmap(matrix=mat)
img_data = pix.tobytes("png")
base64_img = base64.b64encode(img_data).decode()
system_message = (
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

prompt = ChatMessage(content=[SystemMessage(content=system_message),
                            HumanMessage(content={"type": "image_url", "image_url": {"url": f"data:image/png;base64,{base64_img}"}})])
llm_response = llm.invoke(prompt)
print(llm_response.content)