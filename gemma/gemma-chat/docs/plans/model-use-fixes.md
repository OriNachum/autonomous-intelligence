# Model Integration Fixes for Gemma Project

## Overview

This document outlines the specific missing components needed to complete the model integration for the Gemma multimodal AI assistant. The current codebase has placeholder implementations that need to be replaced with actual model integrations.

## Current State Analysis

The codebase shows excellent architecture and structure, but uses placeholder implementations for the core AI models. Here's what needs to be implemented:

## Missing Model Integration Components

### 1. **Gemma 3n Model Integration**

**Current State:** Using DialoGPT-medium as placeholder (line 64-72 in `src/main_loop/model_interface.py`)

**Issues:**
- Not actually loading Gemma 3n model
- Missing multimodal processing pipeline (text + image + audio → text)
- No proper tokenization for multimodal inputs
- Missing model quantization/optimization for Jetson hardware
- No streaming inference capabilities for 400ms target

**Required Implementation:**
```python
# Replace the placeholder with actual Gemma 3n
from transformers import GemmaForCausalLM, GemmaTokenizer
# or appropriate multimodal model classes

class ModelInterface:
    def _initialize_model(self):
        # Load actual Gemma 3n model
        self.tokenizer = GemmaTokenizer.from_pretrained(
            "google/gemma-3n-multimodal",  # Actual model name
            cache_dir=self.model_cache_dir
        )
        
        self.model = GemmaForCausalLM.from_pretrained(
            "google/gemma-3n-multimodal",
            cache_dir=self.model_cache_dir,
            torch_dtype=torch.float16,  # Optimize for Jetson
            device_map="auto"
        )
```

### 2. **SileroVAD Integration**

**Current State:** Import attempt but fallback to mock VAD (line 10-14 in `src/sound_processor/vad_detector.py`)

**Issues:**
- SileroVAD not properly installed
- Missing actual model loading
- No audio preprocessing optimization
- Missing hardware-specific optimizations

**Required Implementation:**
```bash
# Install SileroVAD
pip install silero-vad
# or build from source for Jetson optimization
```

**Code fixes needed:**
```python
# In vad_detector.py
try:
    import torch
    from silero_vad import load_silero_vad, read_audio, get_speech_timestamps
    SILERO_AVAILABLE = True
except ImportError:
    SILERO_AVAILABLE = False

def _load_model(self):
    if SILERO_AVAILABLE:
        self.model, self.utils = load_silero_vad()
        self.logger.info("SileroVAD model loaded successfully")
    else:
        self.logger.warning("SileroVAD not available, using mock VAD")
```

### 3. **KokoroTTS Integration**

**Current State:** Referenced in config but no implementation visible

**Issues:**
- No actual KokoroTTS model loading
- Missing audio synthesis pipeline
- No streaming TTS for real-time performance
- Missing voice configuration and quality settings

**Required Implementation:**
```python
# New file: src/queue_manager/kokoro_tts.py
class KokoroTTSEngine:
    def __init__(self, model_path: str, voice_config: dict):
        """Initialize KokoroTTS engine"""
        self.model_path = model_path
        self.voice_config = voice_config
        self.model = None
        self._load_model()
    
    def _load_model(self):
        """Load KokoroTTS model"""
        try:
            # Load actual KokoroTTS model
            from kokoro_tts import KokoroTTS
            self.model = KokoroTTS.from_pretrained(self.model_path)
            self.logger.info("KokoroTTS model loaded successfully")
        except ImportError:
            self.logger.error("KokoroTTS not available")
    
    async def synthesize_speech(self, text: str) -> bytes:
        """Generate speech audio from text"""
        if self.model is None:
            return b""  # Return empty audio
        
        # Generate speech with streaming capabilities
        audio_data = await self.model.generate_speech(
            text=text,
            voice_config=self.voice_config,
            streaming=True  # Enable streaming for real-time
        )
        return audio_data
```

### 4. **Object Detection Model Integration**

**Current State:** Referenced YOLO but no actual model loading in `src/camera_processor/object_detector.py`

**Issues:**
- No actual YOLO model loading
- Missing human/animal class filtering as specified in plan
- No Jetson-optimized inference (TensorRT)
- Missing object tracking for appearance/disappearance events

**Required Implementation:**
```python
# In object_detector.py
from ultralytics import YOLO

class ObjectDetector:
    def _load_model(self):
        """Load YOLO model"""
        try:
            self.model = YOLO(self.model_path)
            
            # Configure for human/animal detection priority
            self.priority_classes = ['person', 'cat', 'dog', 'bird', 'horse', 'cow']
            
            # Optimize for Jetson if available
            if torch.cuda.is_available():
                self.model.to('cuda')
                # Convert to TensorRT for optimization
                self.model.export(format='engine')
            
            self.logger.info("YOLO model loaded successfully")
        except Exception as e:
            self.logger.error(f"Error loading YOLO model: {e}")
```

### 5. **Model-Specific Dependencies**

**Missing from requirements.txt:**
```txt
# Add to requirements.txt

# For Gemma 3n
google-generativeai==0.3.2
transformers>=4.35.0
torch>=2.0.0
torchvision>=0.15.0
torchaudio>=2.0.0

# For SileroVAD
silero-vad==4.0.0
omegaconf>=2.3.0

# For KokoroTTS
kokoro-tts>=1.0.0  # or appropriate package
espeak-ng  # fallback TTS

# For optimized inference
tensorrt>=8.5.0
onnx>=1.14.0
onnxruntime-gpu>=1.16.0

# For object detection
ultralytics>=8.0.0
```

### 6. **Hardware Optimization**

**Missing optimizations for Jetson:**
```python
# New file: src/optimization/jetson_optimizer.py
class JetsonOptimizer:
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    def optimize_model_for_jetson(self, model):
        """Optimize model for Jetson hardware"""
        try:
            # Convert to TensorRT
            import tensorrt as trt
            
            # Apply quantization
            model = torch.quantization.quantize_dynamic(
                model, {torch.nn.Linear}, dtype=torch.qint8
            )
            
            # Enable CUDA optimizations
            if torch.cuda.is_available():
                model = model.cuda()
                model = torch.jit.script(model)
            
            return model
        except Exception as e:
            self.logger.error(f"Error optimizing model: {e}")
            return model
```

### 7. **Streaming Infrastructure**

**Missing real-time processing components:**
```python
# New file: src/streaming/streaming_pipeline.py
class StreamingPipeline:
    def __init__(self, config):
        self.config = config
        self.response_buffer = []
        self.tts_pipeline = []
    
    async def process_streaming_response(self, model_output):
        """Process streaming model output for real-time TTS"""
        # Extract sentences as they're generated
        sentences = self._extract_sentences(model_output)
        
        # Queue sentences for TTS immediately
        for sentence in sentences:
            if sentence.strip():
                await self._queue_for_tts(sentence)
        
        return sentences
    
    def _extract_sentences(self, text):
        """Extract complete sentences from streaming text"""
        # Implementation for sentence boundary detection
        import re
        sentences = re.split(r'[.!?]+', text)
        return [s.strip() for s in sentences if s.strip()]
```

## Implementation Priority

### High Priority (Critical for Core Functionality)

1. **Complete Gemma 3n Integration**
   - Replace DialoGPT with actual Gemma 3n model
   - Implement multimodal processing pipeline
   - Add proper error handling and fallbacks

2. **Implement SileroVAD**
   - Install and configure SileroVAD properly
   - Replace mock VAD with real implementation
   - Add audio preprocessing optimization

3. **Add KokoroTTS Engine**
   - Implement actual TTS synthesis
   - Add streaming capabilities
   - Configure voice parameters

### Medium Priority (Performance Optimization)

4. **Jetson Hardware Optimization**
   - Add TensorRT optimization
   - Implement model quantization
   - Add GPU memory management

5. **Streaming Response Pipeline**
   - Implement streaming inference
   - Add parallel TTS processing
   - Create response chunking

### Low Priority (Enhancement)

6. **Advanced Object Detection**
   - Add object tracking
   - Implement appearance/disappearance events
   - Add confidence thresholds

## Installation Steps

### 1. Install Model Dependencies
```bash
# Install core dependencies
pip install transformers torch torchvision torchaudio
pip install silero-vad ultralytics

# Install Jetson-specific optimizations
pip install tensorrt onnx onnxruntime-gpu

# Install TTS dependencies
pip install espeak-ng
# pip install kokoro-tts  # when available
```

### 2. Download Models
```bash
# Create models directory
mkdir -p models

# Download YOLO model
wget -O models/yolov6n.pt https://github.com/meituan/YOLOv6/releases/download/0.4.0/yolov6n.pt

# Download Gemma 3n (when available)
# huggingface-cli download google/gemma-3n-multimodal --local-dir models/gemma-3n
```

### 3. Update Configuration
```python
# In config.py, update model paths
MODEL_NAME: str = "google/gemma-3n-multimodal"  # Update to actual model
YOLO_MODEL_PATH: str = "models/yolov6n.pt"
VAD_MODEL_PATH: str = "models/silero_vad"
TTS_MODEL_PATH: str = "models/kokoro_tts"
```

## Testing Integration

### 1. Model Loading Tests
```python
# Test script: test_model_integration.py
async def test_model_loading():
    config = Config.from_env()
    
    # Test each model component
    model_interface = ModelInterface(config)
    assert model_interface.model is not None
    
    vad_detector = VADDetector(config.VAD_MODEL_PATH)
    assert vad_detector.model is not None
    
    # Add tests for each model component
```

### 2. Performance Benchmarks
```python
# Test real-time performance
async def test_400ms_target():
    start_time = time.time()
    
    # Process multimodal input
    response = await model_interface.process_multimodal_input(
        text_input="Hello Gemma",
        image_data=test_image,
        audio_data=test_audio
    )
    
    response_time = time.time() - start_time
    assert response_time < 0.4  # 400ms target
```

## Conclusion

The Gemma project has excellent architecture but needs these model integrations to become fully functional. The priority should be:

1. **Replace placeholder models** with actual implementations
2. **Add streaming capabilities** for real-time performance
3. **Optimize for Jetson hardware** for production deployment

Once these integrations are complete, the system should meet the original 400ms response time target and provide the full multimodal AI assistant experience as planned.