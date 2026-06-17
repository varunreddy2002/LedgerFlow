from langchain_aws import ChatBedrock
from langchain_core.messages import SystemMessage, HumanMessage
from app.core.config import settings
class BedrockService:
    def __init__(self, model_name: str):
        self.model_name = model_name
        self.client = ChatBedrock(model=model_name,
                                  region_name=settings.aws_region,
                                  api_key=settings.aws_api_key,
                                  model_kwargs={"temperature": 0.7, "max_tokens": 2048}
                                  )
    
    def invoke(self, message: str, prompt: str, **args) -> str:
        messages = [
            SystemMessage(content=prompt),
            HumanMessage(content=message)
        ]
        response = self.client.invoke(messages)
        return response.content

bedrock_service = BedrockService(model_name=settings.default_chat_model)