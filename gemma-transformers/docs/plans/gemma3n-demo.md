from transformers import AutoProcessor, Gemma3nForConditionalGeneration
from PIL import Image
import requests
import torch

model_id = "google/gemma-3n-e4b"

model = Gemma3nForConditionalGeneration.from_pretrained(model_id, device="cuda", torch_dtype=torch.bfloat16).eval()

processor = AutoProcessor.from_pretrained(model_id)

url = "https://huggingface.co/datasets/huggingface/documentation-images/resolve/main/bee.jpg"
image = Image.open(requests.get(url, stream=True).raw)
prompt = "<image_soft_token> in this image, there is"
model_inputs = processor(text=prompt, images=image, return_tensors="pt").to(model.device)

input_len = model_inputs["input_ids"].shape[-1]

with torch.inference_mode():
    generation = model.generate(**model_inputs, max_new_tokens=100)
    generation = generation[0][input_len:]

decoded = processor.decode(generation, skip_special_tokens=True)
print(decoded)

#  a bee on a flower.
