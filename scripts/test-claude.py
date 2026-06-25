import base64
import fitz
from langchain_aws import ChatBedrock
from langchain_core.messages import SystemMessage, HumanMessage
import os

DOC_PATH = r"C:\Users\varun\Downloads\Pup Jt - PO.pdf"

SYSTEM_PROMPT = (
    "You are a document layout analyzer. "
    "When given a document image, describe its layout structure concisely. "
    "Identify sections, headers, tables, and where key fields appear on the page. "
    "Do not extract values — just describe the layout."
)


class BedrockService:
    def __init__(self, model_name: str):
        self.model_name = model_name
        self.client = ChatBedrock(model=model_name,
                                  region_name=os.getenv("AWS_REGION"),
                                  api_key=os.getenv("AWS_API_KEY"),
                                  model_kwargs={"temperature": 0.7, "max_tokens": 2048}
                                  )

    def invoke(self, message: str, prompt: str, **args) -> str:
        messages = [
            SystemMessage(content=prompt),
            HumanMessage(content=message)
        ]
        response = self.client.invoke(messages)
        return response.content


bedrock_service = BedrockService(model_name="us.anthropic.claude-haiku-4-5-20251001-v1:0")


def page_to_base64(doc_path: str, page_num: int = 0) -> str:
    doc = fitz.open(doc_path)
    page = doc[page_num]
    pix = page.get_pixmap(matrix=fitz.Matrix(2.0, 2.0))
    img_bytes = pix.tobytes("png")
    doc.close()
    return base64.b64encode(img_bytes).decode()


def extract_layout(image_b64: str) -> str:
    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=[
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/png",
                    "data": image_b64,
                },
            },
            {
                "type": "text",
                "text": "Describe the layout of this document page.",
            },
        ]),
    ]
    response = bedrock_service.client.invoke(messages)
    usage = response.usage_metadata
    print(f"\nTokens — input: {usage['input_tokens']}, output: {usage['output_tokens']}, total: {usage['total_tokens']}")
    return response.content


def main():
    print(f"Document : {DOC_PATH}")
    print(f"Model    : {bedrock_service.model_name}")
    print()

    img_b64 = page_to_base64(DOC_PATH, page_num=0)
    print("Sending page 1 to Claude...\n")

    layout = extract_layout(img_b64)
    print("Layout:\n")
    print(layout)


if __name__ == "__main__":
    main()
