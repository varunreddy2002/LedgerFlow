from app.services.bedrock_service import bedrock_service

response = bedrock_service.invoke(
    message="Hello How are you?. reponse me in 20 words.",
    prompt="You are a helpful assistant.",
    temperature=0.5,
    max_tokens=10)
print(response)