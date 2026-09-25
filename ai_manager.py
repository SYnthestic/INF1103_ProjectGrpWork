import os
from openai import OpenAI

def setup_ai_client():

    api_key = os.getenv("OPENROUTER_API_KEY")
    client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key = api_key
    )
    return client

def get_ai_response():
    client = setup_ai_client()
    response = client.chat.completions.create(
        model="openrouter/free",
        messages=[
            {
                "role": "user",
                "content": "Give me a json formet message. Content can be anything"
            }
        ]
    )
    return response.choices[0].message.content