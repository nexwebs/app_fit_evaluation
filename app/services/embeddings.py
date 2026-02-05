"""
app/services/embeddings.py
Servicio de embeddings ultra-optimizado con cache LRU reducido
"""
import hashlib
from typing import List, Optional
from openai import AsyncOpenAI, OpenAI
import numpy as np
from app.config import settings
import asyncio
from concurrent.futures import ThreadPoolExecutor


class EmbeddingCache:
    
    def __init__(self, max_size: int = 10):
        self.cache = {}
        self.max_size = max_size
        self.access_order = []
    
    def _make_key(self, text: str) -> str:
        return hashlib.md5(text.encode('utf-8')).hexdigest()
    
    def get(self, text: str) -> Optional[List[float]]:
        key = self._make_key(text)
        if key in self.cache:
            if key in self.access_order:
                self.access_order.remove(key)
            self.access_order.append(key)
            return self.cache[key]
        return None
    
    def set(self, text: str, embedding: List[float]):
        key = self._make_key(text)
        
        if len(self.cache) >= self.max_size and key not in self.cache:
            oldest = self.access_order.pop(0)
            del self.cache[oldest]
        
        self.cache[key] = embedding
        if key in self.access_order:
            self.access_order.remove(key)
        self.access_order.append(key)
    
    def clear(self):
        self.cache.clear()
        self.access_order.clear()


class EmbeddingService:
    
    _instance = None
    
    def __init__(self):
        self.async_client = AsyncOpenAI(
            api_key=settings.OPENAI_API_KEY,
            timeout=20.0,
            max_retries=2
        )
        self.sync_client = OpenAI(
            api_key=settings.OPENAI_API_KEY,
            timeout=20.0,
            max_retries=2
        )
        self.cache = EmbeddingCache(max_size=settings.EMBEDDING_CACHE_SIZE)
        self.model = settings.EMBEDDING_MODEL
        self.dimensions = settings.EMBEDDING_DIMENSIONS
        self.executor = ThreadPoolExecutor(max_workers=2)
    
    @classmethod
    def get_instance(cls) -> "EmbeddingService":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    async def embed_text(self, text: str) -> List[float]:
        if not text or not text.strip():
            return [0.0] * self.dimensions
        
        text = text.strip()[:8000]
        
        cached = self.cache.get(text)
        if cached is not None:
            return cached
        
        try:
            response = await self.async_client.embeddings.create(
                model=self.model,
                input=text,
                dimensions=self.dimensions
            )
            
            embedding = response.data[0].embedding
            self.cache.set(text, embedding)
            return embedding
            
        except Exception as e:
            print(f"Error embedding: {e}")
            return [0.0] * self.dimensions
    
    def _sync_embed(self, text: str) -> List[float]:
        if not text or not text.strip():
            return [0.0] * self.dimensions
        
        text = text.strip()[:8000]
        
        cached = self.cache.get(text)
        if cached is not None:
            return cached
        
        try:
            response = self.sync_client.embeddings.create(
                model=self.model,
                input=text,
                dimensions=self.dimensions
            )
            
            embedding = response.data[0].embedding
            self.cache.set(text, embedding)
            return embedding
            
        except Exception as e:
            print(f"Error embedding sync: {e}")
            return [0.0] * self.dimensions
    
    def encode_single(self, text: str) -> List[float]:
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                return self._sync_embed(text)
            else:
                return loop.run_until_complete(self.embed_text(text))
        except RuntimeError:
            return self._sync_embed(text)
    
    def cosine_similarity(self, embedding1: List[float], embedding2: List[float]) -> float:
        vec1 = np.array(embedding1)
        vec2 = np.array(embedding2)
        
        dot_product = np.dot(vec1, vec2)
        norm1 = np.linalg.norm(vec1)
        norm2 = np.linalg.norm(vec2)
        
        if norm1 == 0 or norm2 == 0:
            return 0.0
        
        return float(dot_product / (norm1 * norm2))
    
    def clear_cache(self):
        self.cache.clear()


embedding_service = EmbeddingService.get_instance()