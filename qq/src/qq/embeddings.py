"""Embedding client for generating text embeddings.

Supports:
1. HuggingFace TEI service (Docker) - preferred
2. Local sentence-transformers - fallback for ARM64/Jetson
"""
from typing import List, Optional
import os
import logging

logger = logging.getLogger(__name__)


class EmbeddingClient:
    """Client for generating embeddings via TEI or local sentence-transformers."""
    
    def __init__(
        self,
        tei_url: str | None = None,
        model: str = "text-embeddings-inference",
        local_model: str = "Qwen/Qwen3-Embedding-0.6B",
        prefer_local: bool = False,
    ):
        """
        Initialize the embedding client.
        
        Args:
            tei_url: URL of the TEI OpenAI-compatible API
            model: Model name for TEI
            local_model: sentence-transformers model for local fallback
            prefer_local: If True, use local embeddings even if TEI is available
        """
        self.tei_url = tei_url or os.getenv("TEI_URL", "http://localhost:8101/v1")
        self.model = model
        self.local_model_name = local_model or os.getenv("EMBEDDING_MODEL", "Qwen/Qwen3-Embedding-0.6B")
        self.prefer_local = prefer_local or os.getenv("EMBEDDINGS_LOCAL", "").lower() in ("1", "true", "yes")
        
        self._tei_client: Optional[object] = None
        self._local_model: Optional[object] = None
        self._use_local: Optional[bool] = None
    
    def _init_tei(self) -> bool:
        """Try to initialize TEI client. Returns True if successful."""
        if self._tei_client is not None:
            return True
        
        try:
            from openai import OpenAI
            import httpx
            
            # Quick connectivity check with no retries
            client = OpenAI(
                base_url=self.tei_url,
                api_key="not-needed",
                timeout=httpx.Timeout(2.0, connect=1.0),
                max_retries=0,  # Don't retry - fail fast for connectivity check
            )
            # Test with a simple embedding
            client.embeddings.create(model=self.model, input="test")
            self._tei_client = client
            logger.info("Using TEI service for embeddings")
            return True
        except Exception as e:
            logger.debug(f"TEI not available: {e}")
            print(f"Warning: Failed to connect to embedding service at {self.tei_url}: {e}")
            return False
    
    def _init_local(self) -> bool:
        """Try to initialize local sentence-transformers. Returns True if successful."""
        if self._local_model is not None:
            return True
        
        try:
            from sentence_transformers import SentenceTransformer
            self._local_model = SentenceTransformer(self.local_model_name)
            logger.info(f"Using local embeddings model: {self.local_model_name}")
            return True
        except ImportError:
            logger.warning("sentence-transformers not installed. Run: uv pip install sentence-transformers")
            return False
        except Exception as e:
            logger.warning(f"Failed to load local model: {e}")
            return False
    
    def _ensure_initialized(self) -> bool:
        """Initialize the best available embedding backend."""
        if self._use_local is not None:
            return self._use_local is not None or self._tei_client is not None
        
        if self.prefer_local:
            # When prefer_local is set, ONLY use local - no TEI fallback
            if self._init_local():
                self._use_local = True
                return True
            # Don't try TEI when prefer_local is explicitly set
            self._use_local = None
            return False
        else:
            # Try TEI first, then fallback to local
            if self._init_tei():
                self._use_local = False
                return True
            if self._init_local():
                self._use_local = True
                return True
        
        self._use_local = None
        return False
    
    def get_embedding(self, text: str) -> List[float]:
        """
        Get embedding for a single text.
        
        Args:
            text: Text to embed
            
        Returns:
            List of floats representing the embedding vector
        """
        if not self._ensure_initialized():
            raise RuntimeError("No embedding backend available (TEI or sentence-transformers)")
        
        if self._use_local and self._local_model:
            embedding = self._local_model.encode(text, convert_to_numpy=True)
            return embedding.tolist()
        elif self._tei_client:
            response = self._tei_client.embeddings.create(
                model=self.model,
                input=text,
            )
            return response.data[0].embedding
        else:
            raise RuntimeError("No embedding backend initialized")
    
    def get_embeddings_batch(self, texts: List[str]) -> List[List[float]]:
        """
        Get embeddings for multiple texts in a batch.
        
        Args:
            texts: List of texts to embed
            
        Returns:
            List of embedding vectors
        """
        if not texts:
            return []
        
        if not self._ensure_initialized():
            raise RuntimeError("No embedding backend available (TEI or sentence-transformers)")
        
        if self._use_local and self._local_model:
            embeddings = self._local_model.encode(texts, convert_to_numpy=True)
            return [e.tolist() for e in embeddings]
        elif self._tei_client:
            response = self._tei_client.embeddings.create(
                model=self.model,
                input=texts,
            )
            sorted_data = sorted(response.data, key=lambda x: x.index)
            return [d.embedding for d in sorted_data]
        else:
            raise RuntimeError("No embedding backend initialized")
    
    @property
    def is_available(self) -> bool:
        """Check if any embedding backend is available."""
        return self._ensure_initialized()
    
    @property
    def backend_name(self) -> str:
        """Get the name of the active backend."""
        if self._use_local:
            return f"local:{self.local_model_name}"
        elif self._tei_client:
            return "tei"
        return "none"
