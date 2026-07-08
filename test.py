from pathlib import Path
from app.application.services.ingestion_service import run_ingestion
"""
for name in ["kriwin_bill.pdf", "kriwin_invoice.pdf"]:
    content = Path("scripts") / name
    run_ingestion(business_id=1, filename=name, content=content.read_bytes(), ext=".pdf")




content = Path("scripts/kriwin_bank_statement.csv").read_bytes()
run_ingestion(business_id=1, filename="kriwin_bank_statement.csv", content=content, ext=".csv")


from app.application.agents.categorization.graph import run_categorization
run_categorization(1)



import json
from app.application.agents.pnl.graph import run_pnl

print(json.dumps(run_pnl(1, "2026-06-01", "2026-06-30"), indent=2))

"""
"""
from app.application.agents.chat.chat import run_chat

print(run_chat("What was my net income in June 2026?", business_id=1))
#print(run_chat("Which vendor did I spend the most with?", business_id=1))
#print(run_chat("List my transactions over $1000", business_id=1))

"""

# scripts/test_bedrock.py
import os
import dotenv
dotenv.load_dotenv()

if os.environ.get("AWS_API_KEY"):
    os.environ["AWS_BEARER_TOKEN_BEDROCK"] = os.environ["AWS_API_KEY"]

from langchain_aws import ChatBedrockConverse

model = ChatBedrockConverse(
    model="us.anthropic.claude-haiku-4-5-20251001-v1:0",
    region_name=os.environ.get("AWS_REGION", "us-east-1"),
    temperature=0,
)

response = model.invoke("Say hello in one sentence.")
print(response.content)