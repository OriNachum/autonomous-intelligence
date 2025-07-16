import triton_python_backend_utils as pb_utils
import numpy as np
import torch
from transformers import AutoTokenizer, Gemma3nForConditionalGeneration, AutoProcessor, TextIteratorStreamer
import json
import base64
from PIL import Image
from io import BytesIO
import logging
import os
from threading import Thread
import asyncio

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TritonPythonModel:
    def initialize(self, args):
        self.model_config = json.loads(args['model_config'])
        
        # Get model repository path
        self.model_repository = args['model_repository']
        self.model_version = args['model_version']
        
        # Model name - can be overridden by environment variable
        self.model_name = os.environ.get('MODEL_NAME', 'google/gemma-3n-e4b')
        
        # Initialize device
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        logger.info(f"Using device: {self.device}")
        
        # Load tokenizer and processor
        logger.info(f"Loading processor and tokenizer for {self.model_name}")
        self.processor = AutoProcessor.from_pretrained(self.model_name)
        self.tokenizer = AutoTokenizer.from_pretrained(self.model_name)
        
        # Load model
        logger.info(f"Loading model {self.model_name}")
        self.model = Gemma3nForConditionalGeneration.from_pretrained(
            self.model_name,
            torch_dtype=torch.bfloat16 if torch.cuda.is_available() else torch.float32,
            device_map="auto",
            low_cpu_mem_usage=True
        )
        self.model.eval()
        
        # Default generation parameters
        self.default_max_tokens = 512
        self.default_temperature = 0.7
        self.default_top_p = 0.9
        
        # Decoupled mode flag
        self.decoupled = pb_utils.using_decoupled_model_transaction_policy(
            model_config=self.model_config
        )
        
        logger.info(f"Model initialization complete. Decoupled mode: {self.decoupled}")
    
    def execute(self, requests):
        responses = []
        
        for request in requests:
            # For decoupled mode, we need the response sender
            if self.decoupled:
                response_sender = request.get_response_sender()
            
            # Get inputs
            prompt = pb_utils.get_input_tensor_by_name(request, "prompt")
            prompt_str = prompt.as_numpy()[0].decode('utf-8')
            
            # Optional inputs
            images_tensor = pb_utils.get_input_tensor_by_name(request, "images")
            max_tokens_tensor = pb_utils.get_input_tensor_by_name(request, "max_tokens")
            temperature_tensor = pb_utils.get_input_tensor_by_name(request, "temperature")
            top_p_tensor = pb_utils.get_input_tensor_by_name(request, "top_p")
            stream_tensor = pb_utils.get_input_tensor_by_name(request, "stream")
            
            # Parse optional parameters
            max_tokens = int(max_tokens_tensor.as_numpy()[0]) if max_tokens_tensor else self.default_max_tokens
            temperature = float(temperature_tensor.as_numpy()[0]) if temperature_tensor else self.default_temperature
            top_p = float(top_p_tensor.as_numpy()[0]) if top_p_tensor else self.default_top_p
            stream = bool(stream_tensor.as_numpy()[0]) if stream_tensor else False
            
            # Process images if provided
            images = None
            if images_tensor:
                image_data = images_tensor.as_numpy()
                if len(image_data) > 0 and image_data[0]:
                    try:
                        images = []
                        for img_str in image_data:
                            if img_str:
                                img_bytes = base64.b64decode(img_str.decode('utf-8'))
                                img = Image.open(BytesIO(img_bytes))
                                images.append(img)
                    except Exception as e:
                        logger.error(f"Error processing images: {e}")
                        images = None
            
            # Generate response
            try:
                if images:
                    # Multimodal generation
                    inputs = self.processor(
                        text=prompt_str,
                        images=images,
                        return_tensors="pt"
                    ).to(self.device)
                else:
                    # Text-only generation
                    inputs = self.tokenizer(
                        prompt_str,
                        return_tensors="pt"
                    ).to(self.device)
                
                if stream and self.decoupled:
                    # Streaming generation for decoupled mode
                    streamer = TextIteratorStreamer(
                        self.tokenizer, 
                        skip_prompt=True,
                        skip_special_tokens=True
                    )
                    
                    generation_kwargs = dict(
                        **inputs,
                        max_new_tokens=max_tokens,
                        temperature=temperature,
                        top_p=top_p,
                        do_sample=temperature > 0,
                        pad_token_id=self.tokenizer.pad_token_id,
                        eos_token_id=self.tokenizer.eos_token_id,
                        streamer=streamer
                    )
                    
                    # Start generation in a separate thread
                    thread = Thread(target=self.model.generate, kwargs=generation_kwargs)
                    thread.start()
                    
                    # Stream tokens as they are generated
                    try:
                        for text_chunk in streamer:
                            if text_chunk:
                                output_tensor = pb_utils.Tensor(
                                    "text",
                                    np.array([text_chunk.encode('utf-8')], dtype=np.object_)
                                )
                                response = pb_utils.InferenceResponse(output_tensors=[output_tensor])
                                response_sender.send(response)
                    
                    except Exception as e:
                        logger.error(f"Error during streaming: {e}")
                    
                    finally:
                        # Send final empty response to signal completion
                        response_sender.send(flags=pb_utils.TRITONSERVER_RESPONSE_COMPLETE_FINAL)
                        thread.join()
                    
                else:
                    # Non-streaming generation
                    with torch.no_grad():
                        outputs = self.model.generate(
                            **inputs,
                            max_new_tokens=max_tokens,
                            temperature=temperature,
                            top_p=top_p,
                            do_sample=temperature > 0,
                            pad_token_id=self.tokenizer.pad_token_id,
                            eos_token_id=self.tokenizer.eos_token_id
                        )
                    
                    # Decode response
                    response_text = self.tokenizer.decode(
                        outputs[0][inputs['input_ids'].shape[1]:],
                        skip_special_tokens=True
                    )
                    
                    # Create output tensor
                    output_tensor = pb_utils.Tensor(
                        "text",
                        np.array([response_text.encode('utf-8')], dtype=np.object_)
                    )
                    
                    if self.decoupled:
                        # For decoupled mode, send response and complete
                        response = pb_utils.InferenceResponse(output_tensors=[output_tensor])
                        response_sender.send(response)
                        response_sender.send(flags=pb_utils.TRITONSERVER_RESPONSE_COMPLETE_FINAL)
                    else:
                        # For regular mode, add to responses list
                        inference_response = pb_utils.InferenceResponse(
                            output_tensors=[output_tensor]
                        )
                        responses.append(inference_response)
                
            except Exception as e:
                logger.error(f"Error during generation: {e}")
                error_message = f"Error: {str(e)}"
                output_tensor = pb_utils.Tensor(
                    "text",
                    np.array([error_message.encode('utf-8')], dtype=np.object_)
                )
                
                if self.decoupled:
                    response = pb_utils.InferenceResponse(output_tensors=[output_tensor])
                    response_sender.send(response)
                    response_sender.send(flags=pb_utils.TRITONSERVER_RESPONSE_COMPLETE_FINAL)
                else:
                    inference_response = pb_utils.InferenceResponse(
                        output_tensors=[output_tensor]
                    )
                    responses.append(inference_response)
        
        # Return empty list for decoupled mode, responses for regular mode
        return [] if self.decoupled else responses
    
    def finalize(self):
        logger.info("Cleaning up model")
        del self.model
        del self.processor
        del self.tokenizer
        torch.cuda.empty_cache()