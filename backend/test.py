from openai import OpenAI
import os
from dotenv import load_dotenv

load_dotenv()

endpoint = "https://rg-invoice-review-ae-1.services.ai.azure.com/openai/v1"
deployment_name = "gpt-5.6-terra"
api_key = os.getenv('AZURE_OPENAI_API_KEY')

client = OpenAI(
    base_url=endpoint,
    api_key=api_key
)

response = client.responses.create(
    model=deployment_name,
    input="What is the capital of Vietnam?",
)

print(f"answer: {response.output[0]}")
