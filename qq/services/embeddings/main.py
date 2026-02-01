import os
import logging
from typing import List, Union, Optional
from fastapi import FastAPI, HTTPException, Body
from pydantic import BaseModel
from sentence_transformers import SentenceTransformer

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("embedding-service")

app = FastAPI(title="Local Embedding Service")

# Global model variable
model = None
MODEL_ID = os.getenv("MODEL_ID", "Qwen/Qwen3-Embedding-0.6B")

class EmbeddingRequest(BaseModel):
    input: Union[str, List[str]]
    model: Optional[str] = None
    encoding_format: Optional[str] = "float"

class EmbeddingData(BaseModel):
    object: str = "embedding"
    embedding: List[float]
    index: int

class EmbeddingResponse(BaseModel):
    object: str = "list"
    data: List[EmbeddingData]
    model: str
    usage: dict

@app.on_event("startup")
async def startup_event():
    global model
    logger.info(f"Loading model: {MODEL_ID}")
    try:
        model = SentenceTransformer(MODEL_ID, trust_remote_code=True)
        logger.info("Model loaded successfully")
    except Exception as e:
        logger.error(f"Failed to load model: {e}")
        raise RuntimeError(f"Could not load model {MODEL_ID}")

@app.post("/v1/embeddings", response_model=EmbeddingResponse)
async def create_embeddings(request: EmbeddingRequest):
    if not model:
        raise HTTPException(status_code=503, detail="Model not initialized")
    
    inputs = request.input
    if isinstance(inputs, str):
        inputs = [inputs]
        
    try:
        # Generate embeddings
        embeddings = model.encode(inputs, convert_to_numpy=True)
        embeddings_list = embeddings.tolist()
        
        data = []
        for i, emb in enumerate(embeddings_list):
            data.append(EmbeddingData(
                embedding=emb,
                index=i
            ))
            
        return EmbeddingResponse(
            data=data,
            model=MODEL_ID,
            usage={
                "prompt_tokens": sum(len(s) for s in inputs), # Approximate
                "total_tokens": sum(len(s) for s in inputs)
            }
        )
    except Exception as e:
        logger.error(f"Embedding generation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
async def health_check():
    return {"status": "ok", "model_loaded": model is not None}
