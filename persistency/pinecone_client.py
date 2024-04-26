import os
from pinecone import Pinecone, ServerlessSpec, NotFoundException
from dotenv import load_dotenv
load_dotenv()  # Load environment variables from .env file


dimension = int(os.getenv("PINECONE_DIMENSION"))
index_name = os.getenv("PINECONE_INDEX_NAME")
api_key = os.getenv("PINECONE_API_KEY")
class PineconeService:
    def __init__(self):
        self.client = Pinecone(api_key=api_key)
        self.data = {}

    def init(self):
        index = None
        try:
            index = self.client.Index(index_name)
        except NotFoundException:
            if index is None:
                spec = ServerlessSpec(
                        cloud="aws",
                        region="us-east-1",
                )
                index = self.client.create_index(
                    name=index_name,
                    dimension=dimension,
                    metric="cosine",
                    spec=spec
                )
        return index
        

    def upsert(self, vectors, namespace):
        for vector in vectors:
            self._validate_vector(vector)
        index = self.client.Index(index_name)
        index.upsert(vectors, namespace)

    def remove(self, vector_ids, namespace):
        index = self.client.Index(index_name)
        response = index.delete(
            namespace = namespace,
            ids = vector_ids
        )
        return response

    def find(self, embedding, namespace, top_k=5):
        #self._validate_vector(vector)
        index = self.client.Index(index_name)
        result = index.query(
            namespace = namespace,
            vector = embedding,
            top_k=top_k,
            include_values=True,
            include_metadata=True
        )
        return result
    
    def _validate_vector(self, vector):
        if not isinstance(vector[0], str):
            raise Exception("vector id must be string")
        #if not isinstance(vector[1], [float]):
        #    raise Exception("vector data must be float array")
        if vector[2] is None:
            raise Exception("vector metadata must be defined")

# Example usage:
if __name__ == "__main__":
    ps = PineconeService()
    ps.init()
    ps.remove(("test",[0],{"test": "test"}))
    #ps.remove(("test",[0],None))
    ps.remove((1,[0],None))
