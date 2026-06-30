from langchain_aws import ChatBedrock, ChatBedrockConverse
from langchain_core.messages import SystemMessage, HumanMessage
from app.core.config import settings
class BedrockService:
    def __init__(self, model_name: str, model_kwargs: dict = None):
        self.model_name = model_name
        self.client = ChatBedrock(model=model_name,
                                  region_name=settings.aws_region,
                                  api_key=settings.aws_api_key,
                                  model_kwargs=model_kwargs or {"temperature": 0.7, "max_tokens": 2048}
                                  )
    
    def invoke(self, message: str, prompt: str, **args) -> str:
        messages = [
            SystemMessage(content=prompt),
            HumanMessage(content=message)
        ]
        response = self.client.invoke(messages)
        return response.content

    def invoke_structured(self, message: str, prompt: str, schema, **args):
        messages = [
            SystemMessage(content=prompt),
            HumanMessage(content=message),
        ]
        structured_client = self.client.with_structured_output(schema)
        return structured_client.invoke(messages)

bedrock_service = BedrockService(model_name=settings.default_chat_model)

ocr_client = ChatBedrockConverse(
    model=settings.default_sonnet_model,
    region_name=settings.aws_region,
    temperature=0,
    max_tokens=4000,
)