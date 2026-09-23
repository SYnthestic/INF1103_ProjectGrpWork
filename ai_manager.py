import os
from openai import OpenAI

def setup_ai_client():
    client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=os.environ["OPENROUTER_API_KEY"]
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