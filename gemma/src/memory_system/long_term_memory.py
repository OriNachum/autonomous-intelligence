"""Long-term memory using Milvus and Neo4j"""

import logging
import asyncio
import time
from typing import List, Dict, Any, Optional, Tuple
import json
import numpy as np

from .fact_distiller import Fact

try:
    from pymilvus import connections, Collection, CollectionSchema, FieldSchema, DataType, utility
    MILVUS_AVAILABLE = True
except ImportError:
    MILVUS_AVAILABLE = False
    logging.warning("PyMilvus not available, using mock vector storage")

try:
    from neo4j import GraphDatabase
    NEO4J_AVAILABLE = True
except ImportError:
    NEO4J_AVAILABLE = False
    logging.warning("Neo4j driver not available, using mock graph storage")

try:
    from sentence_transformers import SentenceTransformer
    EMBEDDINGS_AVAILABLE = True
except ImportError:
    EMBEDDINGS_AVAILABLE = False
    logging.warning("SentenceTransformers not available, using mock embeddings")

class LongTermMemory:
    """Long-term memory storage using vector and graph databases"""
    
    def __init__(self, 
                 milvus_host: str = "localhost",
                 milvus_port: int = 19530,
                 neo4j_uri: str = "bolt://localhost:7687",
                 neo4j_user: str = "neo4j",
                 neo4j_password: str = "password",
                 embedding_model: str = "all-MiniLM-L6-v2"):
        
        self.milvus_host = milvus_host
        self.milvus_port = milvus_port
        self.neo4j_uri = neo4j_uri
        self.neo4j_user = neo4j_user
        self.neo4j_password = neo4j_password
        self.embedding_model_name = embedding_model
        
        self.logger = logging.getLogger(__name__)
        
        # Database connections
        self.milvus_collection = None
        self.neo4j_driver = None
        self.embedding_model = None
        
        # Collection configuration
        self.collection_name = "gemma_facts"
        self.embedding_dim = 384  # Default for all-MiniLM-L6-v2
        
        # Statistics
        self.stored_facts = 0
        self.retrieved_facts = 0
        self.embedding_times = []
        self.storage_times = []
        self.retrieval_times = []
        
        # Initialize components
        self._initialize_embeddings()
        self._initialize_milvus()
        self._initialize_neo4j()
    
    def _initialize_embeddings(self):
        """Initialize embedding model"""
        try:
            if EMBEDDINGS_AVAILABLE:
                self.embedding_model = SentenceTransformer(self.embedding_model_name)
                self.embedding_dim = self.embedding_model.get_sentence_embedding_dimension()
                self.logger.info(f"Loaded embedding model: {self.embedding_model_name}")
            else:
                self.logger.warning("Using mock embedding model")
        except Exception as e:
            self.logger.error(f"Error loading embedding model: {e}")
            self.embedding_model = None
    
    def _initialize_milvus(self):
        """Initialize Milvus vector database"""
        try:
            if not MILVUS_AVAILABLE:
                self.logger.warning("Using mock vector storage")
                return
            
            # Connect to Milvus
            connections.connect("default", host=self.milvus_host, port=self.milvus_port)
            
            # Create collection if it doesn't exist
            if not utility.has_collection(self.collection_name):
                self._create_milvus_collection()
            
            # Load collection
            self.milvus_collection = Collection(self.collection_name)
            self.milvus_collection.load()
            
            self.logger.info(f"Connected to Milvus collection: {self.collection_name}")
            
        except Exception as e:
            self.logger.error(f"Error connecting to Milvus: {e}")
            self.milvus_collection = None
    
    def _create_milvus_collection(self):
        """Create Milvus collection schema"""
        fields = [
            FieldSchema(name="id", dtype=DataType.INT64, is_primary=True, auto_id=True),
            FieldSchema(name="fact_id", dtype=DataType.VARCHAR, max_length=256),
            FieldSchema(name="content", dtype=DataType.VARCHAR, max_length=2048),
            FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=self.embedding_dim),
            FieldSchema(name="category", dtype=DataType.VARCHAR, max_length=64),
            FieldSchema(name="importance", dtype=DataType.FLOAT),
            FieldSchema(name="confidence", dtype=DataType.FLOAT),
            FieldSchema(name="timestamp", dtype=DataType.DOUBLE),
            FieldSchema(name="source", dtype=DataType.VARCHAR, max_length=128),
            FieldSchema(name="metadata", dtype=DataType.VARCHAR, max_length=1024)
        ]
        
        schema = CollectionSchema(fields, description="Gemma fact storage")
        collection = Collection(self.collection_name, schema)
        
        # Create index for vector search
        index_params = {
            "metric_type": "IP",  # Inner Product
            "index_type": "IVF_FLAT",
            "params": {"nlist": 128}
        }
        collection.create_index("embedding", index_params)
        
        self.logger.info(f"Created Milvus collection: {self.collection_name}")
    
    def _initialize_neo4j(self):
        """Initialize Neo4j graph database"""
        try:
            if not NEO4J_AVAILABLE:
                self.logger.warning("Using mock graph storage")
                return
            
            self.neo4j_driver = GraphDatabase.driver(
                self.neo4j_uri,
                auth=(self.neo4j_user, self.neo4j_password)
            )
            
            # Test connection
            with self.neo4j_driver.session() as session:
                session.run("RETURN 1")
            
            # Create constraints and indexes
            self._create_neo4j_schema()
            
            self.logger.info("Connected to Neo4j")
            
        except Exception as e:
            self.logger.error(f"Error connecting to Neo4j: {e}")
            self.neo4j_driver = None
    
    def _create_neo4j_schema(self):
        """Create Neo4j schema"""
        try:
            with self.neo4j_driver.session() as session:
                # Create constraints
                session.run("""
                    CREATE CONSTRAINT fact_id_unique IF NOT EXISTS 
                    FOR (f:Fact) REQUIRE f.id IS UNIQUE
                """)
                
                session.run("""
                    CREATE CONSTRAINT category_name_unique IF NOT EXISTS 
                    FOR (c:Category) REQUIRE c.name IS UNIQUE
                """)
                
                # Create indexes
                session.run("""
                    CREATE INDEX fact_timestamp IF NOT EXISTS 
                    FOR (f:Fact) ON (f.timestamp)
                """)
                
                session.run("""
                    CREATE INDEX fact_importance IF NOT EXISTS 
                    FOR (f:Fact) ON (f.importance)
                """)
                
            self.logger.info("Created Neo4j schema")
            
        except Exception as e:
            self.logger.error(f"Error creating Neo4j schema: {e}")
    
    async def store_fact(self, fact: Fact) -> bool:
        """Store a fact in long-term memory"""
        start_time = time.time()
        
        try:
            # Generate unique fact ID
            fact_id = f"{fact.source}_{int(fact.timestamp)}_{hash(fact.content) % 10000}"
            
            # Generate embedding
            embedding = await self._generate_embedding(fact.content)
            if embedding is None:
                return False
            
            # Store in vector database
            vector_success = await self._store_in_milvus(fact, fact_id, embedding)
            
            # Store in graph database
            graph_success = await self._store_in_neo4j(fact, fact_id)
            
            if vector_success or graph_success:  # Success if at least one storage method works
                self.stored_facts += 1
                storage_time = time.time() - start_time
                self.storage_times.append(storage_time)
                
                if len(self.storage_times) > 100:
                    self.storage_times.pop(0)
                
                self.logger.debug(f"Stored fact in long-term memory: {fact.content[:50]}...")
                return True
            
        except Exception as e:
            self.logger.error(f"Error storing fact: {e}")
        
        return False
    
    async def _generate_embedding(self, text: str) -> Optional[np.ndarray]:
        """Generate embedding for text"""
        start_time = time.time()
        
        try:
            if self.embedding_model:
                embedding = self.embedding_model.encode([text])[0]
                
                embedding_time = time.time() - start_time
                self.embedding_times.append(embedding_time)
                
                if len(self.embedding_times) > 100:
                    self.embedding_times.pop(0)
                
                return embedding
            else:
                # Mock embedding
                return np.random.random(self.embedding_dim).astype(np.float32)
                
        except Exception as e:
            self.logger.error(f"Error generating embedding: {e}")
            return None
    
    async def _store_in_milvus(self, fact: Fact, fact_id: str, embedding: np.ndarray) -> bool:
        """Store fact in Milvus vector database"""
        try:
            if not self.milvus_collection:
                return False
            
            # Prepare data
            data = [
                [fact_id],
                [fact.content],
                [embedding.tolist()],
                [fact.category],
                [fact.importance],
                [fact.confidence],
                [fact.timestamp],
                [fact.source],
                [json.dumps({"related_facts": fact.related_facts})]
            ]
            
            # Insert data
            mr = self.milvus_collection.insert(data)
            self.milvus_collection.flush()
            
            return len(mr.primary_keys) > 0
            
        except Exception as e:
            self.logger.error(f"Error storing in Milvus: {e}")
            return False
    
    async def _store_in_neo4j(self, fact: Fact, fact_id: str) -> bool:
        """Store fact in Neo4j graph database"""
        try:
            if not self.neo4j_driver:
                return False
            
            with self.neo4j_driver.session() as session:
                # Create fact node
                session.run("""
                    MERGE (f:Fact {id: $fact_id})
                    SET f.content = $content,
                        f.category = $category,
                        f.importance = $importance,
                        f.confidence = $confidence,
                        f.timestamp = $timestamp,
                        f.source = $source
                """, {
                    "fact_id": fact_id,
                    "content": fact.content,
                    "category": fact.category,
                    "importance": fact.importance,
                    "confidence": fact.confidence,
                    "timestamp": fact.timestamp,
                    "source": fact.source
                })
                
                # Create category node and relationship
                session.run("""
                    MERGE (c:Category {name: $category})
                    WITH c
                    MATCH (f:Fact {id: $fact_id})
                    MERGE (f)-[:BELONGS_TO]->(c)
                """, {
                    "category": fact.category,
                    "fact_id": fact_id
                })
                
                # Create source node and relationship
                session.run("""
                    MERGE (s:Source {name: $source})
                    WITH s
                    MATCH (f:Fact {id: $fact_id})
                    MERGE (f)-[:ORIGINATED_FROM]->(s)
                """, {
                    "source": fact.source,
                    "fact_id": fact_id
                })
            
            return True
            
        except Exception as e:
            self.logger.error(f"Error storing in Neo4j: {e}")
            return False
    
    async def search_facts(self, 
                          query: str,
                          max_results: int = 10,
                          similarity_threshold: float = 0.7) -> List[Fact]:
        """Search for facts using semantic similarity"""
        start_time = time.time()
        
        try:
            # Generate query embedding
            query_embedding = await self._generate_embedding(query)
            if query_embedding is None:
                return []
            
            # Search in Milvus
            facts = await self._search_milvus(query_embedding, max_results, similarity_threshold)
            
            # Update statistics
            self.retrieved_facts += len(facts)
            retrieval_time = time.time() - start_time
            self.retrieval_times.append(retrieval_time)
            
            if len(self.retrieval_times) > 100:
                self.retrieval_times.pop(0)
            
            self.logger.debug(f"Retrieved {len(facts)} facts for query: {query[:30]}...")
            
            return facts
            
        except Exception as e:
            self.logger.error(f"Error searching facts: {e}")
            return []
    
    async def _search_milvus(self, 
                           query_embedding: np.ndarray,
                           max_results: int,
                           similarity_threshold: float) -> List[Fact]:
        """Search Milvus for similar facts"""
        try:
            if not self.milvus_collection:
                return []
            
            # Search parameters
            search_params = {
                "metric_type": "IP",
                "params": {"nprobe": 10}
            }
            
            # Perform search
            results = self.milvus_collection.search(
                [query_embedding.tolist()],
                "embedding",
                search_params,
                limit=max_results,
                output_fields=["fact_id", "content", "category", "importance", 
                              "confidence", "timestamp", "source", "metadata"]
            )
            
            # Convert results to Fact objects
            facts = []
            for hits in results:
                for hit in hits:
                    if hit.score >= similarity_threshold:
                        entity = hit.entity
                        
                        # Parse metadata
                        metadata = {}
                        try:
                            metadata = json.loads(entity.get('metadata', '{}'))
                        except:
                            pass
                        
                        fact = Fact(
                            content=entity.get('content'),
                            confidence=entity.get('confidence'),
                            timestamp=entity.get('timestamp'),
                            source=entity.get('source'),
                            category=entity.get('category'),
                            importance=entity.get('importance'),
                            related_facts=metadata.get('related_facts', [])
                        )
                        facts.append(fact)
            
            return facts
            
        except Exception as e:
            self.logger.error(f"Error searching Milvus: {e}")
            return []
    
    async def get_related_facts(self, fact_id: str, max_depth: int = 2) -> List[Dict[str, Any]]:
        """Get related facts using graph traversal"""
        try:
            if not self.neo4j_driver:
                return []
            
            with self.neo4j_driver.session() as session:
                result = session.run("""
                    MATCH (f:Fact {id: $fact_id})
                    CALL apoc.path.subgraphNodes(f, {
                        relationshipFilter: "<RELATED_TO|SIMILAR_TO>",
                        maxLevel: $max_depth
                    })
                    YIELD node
                    WHERE node:Fact AND node.id <> $fact_id
                    RETURN node.id as id, node.content as content, 
                           node.importance as importance
                    ORDER BY node.importance DESC
                    LIMIT 10
                """, {"fact_id": fact_id, "max_depth": max_depth})
                
                related_facts = []
                for record in result:
                    related_facts.append({
                        "id": record["id"],
                        "content": record["content"],
                        "importance": record["importance"]
                    })
                
                return related_facts
                
        except Exception as e:
            self.logger.error(f"Error getting related facts: {e}")
            return []
    
    async def archive_facts(self, facts: List[Fact]) -> int:
        """Archive multiple facts to long-term storage"""
        archived_count = 0
        
        for fact in facts:
            if await self.store_fact(fact):
                archived_count += 1
        
        self.logger.info(f"Archived {archived_count} facts to long-term memory")
        return archived_count
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get long-term memory statistics"""
        avg_embedding_time = (sum(self.embedding_times) / len(self.embedding_times) 
                             if self.embedding_times else 0)
        avg_storage_time = (sum(self.storage_times) / len(self.storage_times) 
                           if self.storage_times else 0)
        avg_retrieval_time = (sum(self.retrieval_times) / len(self.retrieval_times) 
                             if self.retrieval_times else 0)
        
        return {
            'milvus_connected': self.milvus_collection is not None,
            'neo4j_connected': self.neo4j_driver is not None,
            'embedding_model_loaded': self.embedding_model is not None,
            'stored_facts': self.stored_facts,
            'retrieved_facts': self.retrieved_facts,
            'avg_embedding_time': avg_embedding_time,
            'avg_storage_time': avg_storage_time,
            'avg_retrieval_time': avg_retrieval_time,
            'embedding_dimension': self.embedding_dim
        }
    
    async def close(self):
        """Close database connections"""
        try:
            if self.neo4j_driver:
                self.neo4j_driver.close()
            
            if MILVUS_AVAILABLE:
                connections.disconnect("default")
            
            self.logger.info("Closed long-term memory connections")
            
        except Exception as e:
            self.logger.error(f"Error closing connections: {e}")