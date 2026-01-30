from openai import OpenAI

# Initialize OpenAI client pointing to local vLLM server
client = OpenAI(
    base_url="http://localhost:8100/v1",
    api_key="EMPTY"  # vLLM doesn't require an API key by default
)

import os

model_id = os.getenv("MODEL_ID", "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-FP8")

print(f"Testing vLLM server with model: {model_id}")

try:
    completion = client.chat.completions.create(
        model=model_id,
        messages=[
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Hello! Can you tell me what follows A, B, C?"}
        ],
        temperature=0.7,
        max_tokens=100
    )
    
    print("\nResponse:")
    print(completion.choices[0].message.content)
    print("\nTest passed successfully!")

except Exception as e:
    print(f"\nTest failed with error: {e}")
