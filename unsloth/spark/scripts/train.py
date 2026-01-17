#!/usr/bin/env python3
"""
Configurable Unsloth fine-tuning script.
Settings are read from environment variables (set via .env file).
"""

import os
from unsloth import FastLanguageModel, FastModel
import torch
from trl import SFTTrainer, SFTConfig
from datasets import load_dataset

# Read settings from environment
MODEL_NAME = os.getenv("MODEL_NAME", "unsloth/gemma-3-4B-it")
MAX_SEQ_LENGTH = int(os.getenv("MAX_SEQ_LENGTH", "2048"))
LOAD_IN_4BIT = os.getenv("LOAD_IN_4BIT", "true").lower() == "true"
BATCH_SIZE = int(os.getenv("BATCH_SIZE", "2"))
GRADIENT_ACCUMULATION_STEPS = int(os.getenv("GRADIENT_ACCUMULATION_STEPS", "4"))
MAX_STEPS = int(os.getenv("MAX_STEPS", "60"))
LEARNING_RATE = float(os.getenv("LEARNING_RATE", "5e-5"))
LORA_R = int(os.getenv("LORA_R", "16"))
LORA_ALPHA = int(os.getenv("LORA_ALPHA", "16"))
HF_TOKEN = os.getenv("HF_TOKEN", None)

print(f"=== Unsloth Training Configuration ===")
print(f"Model: {MODEL_NAME}")
print(f"Max Seq Length: {MAX_SEQ_LENGTH}")
print(f"4-bit Quantization: {LOAD_IN_4BIT}")
print(f"Batch Size: {BATCH_SIZE}")
print(f"Gradient Accumulation: {GRADIENT_ACCUMULATION_STEPS}")
print(f"Max Steps: {MAX_STEPS}")
print(f"LoRA r={LORA_R}, alpha={LORA_ALPHA}")
print(f"======================================\n")

# Load dataset - default to LAION OIG for testing
# Override by placing your dataset in /workspace/data/
data_path = "/workspace/data/train.jsonl"
if os.path.exists(data_path):
    print(f"Loading custom dataset from {data_path}")
    dataset = load_dataset("json", data_files={"train": data_path}, split="train")
else:
    print("Loading default LAION OIG dataset...")
    url = "https://huggingface.co/datasets/laion/OIG/resolve/main/unified_chip2.jsonl"
    dataset = load_dataset("json", data_files={"train": url}, split="train")

# Load model
model_kwargs = {
    "model_name": MODEL_NAME,
    "max_seq_length": MAX_SEQ_LENGTH,
    "load_in_4bit": LOAD_IN_4BIT,
    "load_in_8bit": False,
    "full_finetuning": False,
}
if HF_TOKEN:
    model_kwargs["token"] = HF_TOKEN

model, tokenizer = FastModel.from_pretrained(**model_kwargs)

# Add LoRA adapters
model = FastLanguageModel.get_peft_model(
    model,
    r=LORA_R,
    target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                    "gate_proj", "up_proj", "down_proj"],
    lora_alpha=LORA_ALPHA,
    lora_dropout=0,
    bias="none",
    use_gradient_checkpointing="unsloth",
    random_state=3407,
    max_seq_length=MAX_SEQ_LENGTH,
    use_rslora=False,
    loftq_config=None,
)

# Train
trainer = SFTTrainer(
    model=model,
    train_dataset=dataset,
    tokenizer=tokenizer,
    args=SFTConfig(
        max_seq_length=MAX_SEQ_LENGTH,
        per_device_train_batch_size=BATCH_SIZE,
        gradient_accumulation_steps=GRADIENT_ACCUMULATION_STEPS,
        warmup_steps=10,
        max_steps=MAX_STEPS,
        learning_rate=LEARNING_RATE,
        logging_steps=1,
        output_dir="/workspace/outputs",
        optim="adamw_8bit",
        seed=3407,
    ),
)

trainer.train()
print("\n✅ Training complete! Model saved to /workspace/outputs")
