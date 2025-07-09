import os
import sys
import torch
from typing import Optional, Dict, AsyncGenerator
from PIL import Image
from transformers import AutoProcessor, Gemma3nForConditionalGeneration
from huggingface_hub import login
import asyncio


class ModelHandler:
    def __init__(self):
        self.model_id = os.getenv("MODEL_NAME", "google/gemma-3n-e4b")
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        
        # Check for HF token if needed
        hf_token = os.getenv("HUGGING_FACE_HUB_TOKEN", os.getenv("HF_TOKEN"))
        if hf_token:
            print("Logging in to Hugging Face Hub...")
            try:
                login(token=hf_token)
            except Exception as e:
                print(f"Warning: Failed to login to HF Hub: {e}")
        
        # Get cache directory
        self.cache_dir = os.getenv('HF_HOME', '/cache/huggingface')
        
        print(f"Loading model {self.model_id} on {self.device}...")
        print(f"Model cache dir: {self.cache_dir}")
        
        # Load model with appropriate dtype
        dtype = torch.bfloat16 if self.device == "cuda" else torch.float32
        
        try:
            # First try to load the processor
            print("Loading processor...")
            self.processor = AutoProcessor.from_pretrained(self.model_id, cache_dir=self.cache_dir)
            
            # Then load the model
            print("Loading model weights...")
            self.model = Gemma3nForConditionalGeneration.from_pretrained(
                self.model_id,
                device_map=self.device,
                torch_dtype=dtype,
                low_cpu_mem_usage=True,
                cache_dir=self.cache_dir
            ).eval()
            
            print(f"✓ Model loaded successfully on {self.device}")
            
            # Print model info
            total_params = sum(p.numel() for p in self.model.parameters())
            print(f"Model parameters: {total_params:,}")
            
        except Exception as e:
            print(f"✗ Failed to load model: {e}")
            print("\nTroubleshooting:")
            print("1. Run 'python download_model.py' to pre-download the model")
            print("2. If the model is gated, ensure HF_TOKEN is set")
            print("3. Check your internet connection")
            print("4. Verify sufficient disk space and GPU memory")
            raise
    
    def prepare_input(self, prompt: str, image: Optional[Image.Image] = None) -> Dict:
        """Prepare input for the model."""
        if image is not None:
            # Multimodal input with image
            # Use the special image token as shown in the example
            full_prompt = f"<image_soft_token> {prompt}"
            model_inputs = self.processor(
                text=full_prompt,
                images=image,
                return_tensors="pt"
            ).to(self.model.device)
        else:
            # Text-only input
            model_inputs = self.processor(
                text=prompt,
                return_tensors="pt"
            ).to(self.model.device)
        
        return model_inputs
    
    async def generate(
        self,
        prompt: str,
        image: Optional[Image.Image] = None,
        generation_params: Optional[Dict] = None
    ) -> str:
        """Generate response for the given prompt and optional image."""
        if generation_params is None:
            generation_params = {}
        
        # Prepare inputs
        model_inputs = self.prepare_input(prompt, image)
        input_len = model_inputs["input_ids"].shape[-1]
        
        # Set default generation parameters
        gen_params = {
            "max_new_tokens": generation_params.get("max_new_tokens", 100),
            "temperature": generation_params.get("temperature", 0.7),
            "top_p": generation_params.get("top_p", 1.0),
            "do_sample": generation_params.get("temperature", 0.7) > 0,
        }
        
        # Generate
        with torch.inference_mode():
            generation = self.model.generate(**model_inputs, **gen_params)
            # Extract only the generated tokens
            generation = generation[0][input_len:]
        
        # Decode
        decoded = self.processor.decode(generation, skip_special_tokens=True)
        return decoded
    
    async def generate_stream(
        self,
        prompt: str,
        image: Optional[Image.Image] = None,
        generation_params: Optional[Dict] = None
    ) -> AsyncGenerator[str, None]:
        """Generate streaming response for the given prompt and optional image."""
        if generation_params is None:
            generation_params = {}
        
        # Prepare inputs
        model_inputs = self.prepare_input(prompt, image)
        input_len = model_inputs["input_ids"].shape[-1]
        
        # Set generation parameters for streaming
        gen_params = {
            "max_new_tokens": generation_params.get("max_new_tokens", 100),
            "temperature": generation_params.get("temperature", 0.7),
            "top_p": generation_params.get("top_p", 1.0),
            "do_sample": generation_params.get("temperature", 0.7) > 0,
        }
        
        # For streaming, we'll generate token by token
        # This is a simplified approach - in production you might want to use
        # a more sophisticated streaming method
        
        generated_tokens = []
        past_key_values = None
        
        with torch.inference_mode():
            for _ in range(gen_params["max_new_tokens"]):
                # Prepare inputs for next token generation
                if past_key_values is None:
                    inputs = model_inputs
                else:
                    # Use only the last generated token as input
                    inputs = {
                        "input_ids": generated_tokens[-1].unsqueeze(0).unsqueeze(0),
                        "attention_mask": torch.ones(1, len(generated_tokens) + input_len, device=self.model.device),
                    }
                
                # Generate next token
                outputs = self.model(
                    **inputs,
                    past_key_values=past_key_values,
                    use_cache=True,
                    return_dict=True
                )
                
                past_key_values = outputs.past_key_values
                logits = outputs.logits[0, -1, :]
                
                # Apply temperature
                if gen_params["temperature"] > 0:
                    logits = logits / gen_params["temperature"]
                
                # Sample next token
                if gen_params["do_sample"]:
                    probs = torch.softmax(logits, dim=-1)
                    next_token = torch.multinomial(probs, num_samples=1)
                else:
                    next_token = torch.argmax(logits, dim=-1, keepdim=True)
                
                generated_tokens.append(next_token)
                
                # Decode the new token
                token_text = self.processor.decode(next_token, skip_special_tokens=True)
                
                # Check for end of sequence
                if next_token.item() == self.processor.tokenizer.eos_token_id:
                    break
                
                if token_text:
                    yield token_text
                
                # Allow other async tasks to run
                await asyncio.sleep(0)