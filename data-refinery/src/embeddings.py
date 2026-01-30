"""Embedding client for generating text embeddings using TEI."""
from typing import List, Optional
from openai import OpenAI


class EmbeddingClient:
    """Client for generating embeddings via HuggingFace TEI service."""
    
    def __init__(
        self,
        tei_url: str = "http://localhost:8101/v1",
        model: str = "text-embeddings-inference",
    ):
        """
        Initialize the embedding client.
        
        Args:
            tei_url: URL of the TEI OpenAI-compatible API
            model: Model name (TEI uses "text-embeddings-inference" by default)
        """
        self.client = OpenAI(base_url=tei_url, api_key="not-needed")
        self.model = model
    
    def get_embedding(self, text: str) -> List[float]:
        """
        Get embedding for a single text.
        
        Args:
            text: Text to embed
            
        Returns:
            List of floats representing the embedding vector
        """
        response = self.client.embeddings.create(
            model=self.model,
            input=text,
        )
        return response.data[0].embedding
    
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
        
        response = self.client.embeddings.create(
            model=self.model,
            input=texts,
        )
        # Sort by index to ensure correct order
        sorted_data = sorted(response.data, key=lambda x: x.index)
        return [d.embedding for d in sorted_data]
    
    def embed_entity(self, name: str, description: str) -> List[float]:
        """
        Generate embedding for an entity using its name and description.
        
        Args:
            name: Entity name
            description: Entity description
            
        Returns:
            Embedding vector
        """
        text = f"{name}: {description}"
        return self.get_embedding(text)
