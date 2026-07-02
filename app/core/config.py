from pydantic_settings import BaseSettings
import os
import dotenv

# Load .env into os.environ so boto3 (Bedrock) can find AWS credentials
# such as AWS_BEARER_TOKEN_BEDROCK. pydantic reads .env for its own fields,
# but boto3 reads from the process environment — this bridges the two.
dotenv.load_dotenv()

# boto3 (Bedrock) looks for AWS_BEARER_TOKEN_BEDROCK. We store the key as
# AWS_API_KEY, so mirror it into the name boto3 expects if not already set.
if os.environ.get("AWS_API_KEY") and not os.environ.get("AWS_BEARER_TOKEN_BEDROCK"):
    os.environ["AWS_BEARER_TOKEN_BEDROCK"] = os.environ["AWS_API_KEY"]


class Settings(BaseSettings):
    database_url: str = "postgresql://postgres:postgres@localhost:5432/ledgerflow"
    upload_dir: str = "./uploads"
    debug: bool = True

    # Categorization engine thresholds
    # Transactions with confidence >= this value are auto-approved;
    # below it they stay as needs_review for human inspection.
    categorization_confidence_threshold: float = 0.75

    # Transactions with an absolute amount above this value always get a
    # large_transaction ReviewItem regardless of confidence score.
    large_transaction_threshold: float = 5000.0

    # Seconds before the in-process categorization rule cache expires.
    # On expiry the engine reloads rules from the DB on next use.
    rule_cache_ttl_seconds: int = 300  # 5 minutes

    # OCR — vLLM (RunPod or EC2, OpenAI-compatible)
    ocr_provider: str = "vllm"
    vllm_base_url: str = ""
    vllm_api_key: str = ""
    ocr_model: str = "h2oai/h2ovl-mississippi-800m"

    # Chat — which provider to use ("bedrock" or "openai")
    chat_provider: str = "bedrock"
    default_chat_model: str = "us.anthropic.claude-haiku-4-5-20251001-v1:0"
    default_sonnet_model: str = "us.anthropic.claude-sonnet-4-5-20250929-v1:0"

    # Embedding — which provider to use ("bedrock")
    embedding_provider: str = "bedrock"
    embedding_model: str = "amazon.titan-embed-text-v2:0"

    # AWS — used by Bedrock (chat + embedding)
    aws_region: str = "us-east-1"
    aws_api_key: str = os.environ.get("AWS_API_KEY")

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


settings = Settings()
