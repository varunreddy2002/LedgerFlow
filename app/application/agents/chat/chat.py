from langchain_aws import ChatBedrockConverse
from langchain.agents import create_agent

from app.core.config import settings
from app.core.logging import get_logger
from app.application.agents.chat.tool import query_database, get_pnl

logger = get_logger(__name__)

# Haiku via the Converse API — reliable tool calling
chat_model = ChatBedrockConverse(
    model=settings.default_chat_model,
    region_name=settings.aws_region,
    temperature=0,
)

SCHEMA = """
DATABASE SCHEMA (PostgreSQL). Every table has an integer primary key `id`.

========== CORE FINANCIAL TABLES (use these for finance questions) ==========

businesses(id, name, business_type, currency)

accounts(id, business_id, account_name, account_type, institution_name, last_four, currency)
    - account_type: 'checking' | 'savings' | 'credit_card' | 'cash' | 'other'

documents(id, business_id, party_id, source, filename, status, uploaded_at, processed_at)
    - source: 'bank_statement' | 'credit_card' | 'vendor_bill' | 'invoice'
    - status: 'uploaded' | 'processing' | 'processed' | 'failed'

transactions(id, document_id, party_id, vendor_id, customer_id, description,
             date, due_date, amount, trans_type, category_id, review_status, fingerprint_hash)
    - amount: NUMERIC, always POSITIVE
    - trans_type: 'debit' (money OUT) | 'credit' (money IN)
    - review_status: 'uncategorized' | 'needs_review' | 'auto_approved' | 'user_approved' | 'user_corrected' | 'ignored'
    - transactions have NO business_id -> join documents to scope by business
    - FKs: document_id->documents.id, category_id->categories.id, vendor_id->vendors.id, customer_id->customers.id

transaction_line_items(id, transaction_id, description, quantity, unit_price, tax_amount, category_id, review_status)
    - FKs: transaction_id->transactions.id, category_id->categories.id

categories(id, business_id, name, parent_category_id, category_type)
    - category_type: 'revenue' | 'expense' | 'transfer' | 'owner_draw'

vendors(id, business_id, name)
customers(id, business_id, name)

document_extractions(id, document_id, extraction_type, raw_text, extracted_json, model_used, confidence_score)
    - raw OCR/LLM output per document (audit trail); extracted_json is JSON

categorization_rules(id, business_id, pattern, match_field, category_id, confidence, priority, is_system)
    - regex rules that auto-assign categories

========== SYSTEM TABLES (ignore unless explicitly asked) ==========

users(id, business_id, name, email, is_active)
chat_sessions(id, thread_id, business_id, user_id, title)
chat_messages(id, session_id, role, message, agent_name, token_usage, metadata_json)
audit_logs(id, business_id, user_id, action, entity_type, entity_id, old_value, new_value)

========== KEY RULES ==========
- Scope transactions to a business by joining documents:
      JOIN documents d ON d.id = transactions.document_id  WHERE d.business_id = <business_id>
- categories, vendors, customers, accounts have business_id directly.
- Bank / cash rows:  d.source IN ('bank_statement','credit_card')
- Invoices / bills:  d.source IN ('vendor_bill','invoice')
- Cash-basis P&L counts only bank/cash rows; invoices/bills are expectations, not cash.
"""

SYSTEM_PROMPT = f"""You are a financial analyst assistant for a small business.

You have two tools:
- get_pnl: use for profit/loss, net income, total revenue, or total expenses over a period.
- query_database: use for any other question. Write a single read-only PostgreSQL SELECT.

{SCHEMA}

Always filter by the business_id you are given. Be concise and answer in plain language,
citing the numbers you found. If a query returns an error, fix it and try again.
"""

agent = create_agent(
    model=chat_model,
    tools=[query_database, get_pnl],
    system_prompt=SYSTEM_PROMPT,
)


def run_chat(message: str, business_id: int) -> str:
    """Answer a natural-language question about the business's finances."""
    logger.info("Chat: business_id=%s q=%s", business_id, message)

    result = agent.invoke({
        "messages": [
            {"role": "user", "content": f"business_id = {business_id}\n\nQuestion: {message}"}
        ]
    })

    answer = result["messages"][-1].content
    logger.info("Chat answered business_id=%s", business_id)
    return answer