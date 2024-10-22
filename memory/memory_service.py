import sys
import os
import datetime

if __name__ == "__main__":
    parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if parent_dir not in sys.path:
        sys.path.append(parent_dir)
        
from persistency.pinecone_client import PineconeService
from persistency.voyageai_client import embed, embed_many

class MemoryService:
    def __init__(self):
        self.pinecone_service = PineconeService()

    def remember(self, fact, namespace):
        model = "voyage-2"
        
        embedding = embed(fact, model=model, purpose="document")
        # Get the current UTC time
        utc_now = datetime.datetime.utcnow()

        # Convert UTC time to a timestamp
        timestamp = int(utc_now.timestamp())

        self.pinecone_service.upsert([(f"{timestamp}",embedding, { "text": fact, "model": model })], namespace)

    def remember_many(self, facts, namespace):
        model = "voyage-2"

        embeddings = embed_many(facts, model=model, purpose="document")

        # Get the current UTC time
        utc_now = datetime.datetime.utcnow()

        # Convert UTC time to a timestamp
        timestamp = int(utc_now.timestamp())
        
        vectors = [(f"{timestamp}-{i}",embeddings[i], { "text": facts[i], "model": model }) for i  in range(0, len(embeddings))]
        #for vector, i in vectors:
        #    vector[2].text=facts[i]
        self.pinecone_service.upsert(vectors, namespace)


    def retrieve_relevant_memories(self, query, namespace, top_k=5):
        embedding = embed(query, model="voyage-2", purpose="document")
        results = self.pinecone_service.find(embedding, namespace, top_k)
        #print("Find results:", results)
        remembered_facts = [(item.id, item.score, item.values, len(item.values), item.metadata) for item in results.matches]
        return remembered_facts

    def forget(self, fact, namespace):
        embeddings_to_forget = self.do_you_remember(fact, namespace)
        ids = [item[0] for item in remembered_facts if item[1] > 0.95]        
        response = self.pinecone_service.remove(ids, namespace)
        return response

# Example usage:
if __name__ == "__main__":
    ms = MemoryService()
    ms.remember("The capital of France is Paris.", "facts")
    ms.remember("The capital of Israel is Jerusalem.", "facts")
    ms.remember_many(["The capital of France is Paris.", "The capital of Israel is Jerusalem."], "facts")
    remembered_facts = ms.retrieve_relevant_memories("What is the capital of France?", "facts")
    print("Remembered facts:", [(item[0], item[1], item[3], item[4]) for item in remembered_facts], "\n\n")
    forget_response = ms.forget("Paris is the capital of France.", "facts")
    print(forget_response)
    remembered_facts = ms.retrieve_relevant_memories("The capital of Israel is Jerusalem.", "facts")
    print("Remembered facts after deletion:", [(item[0], item[1], item[3], item[4]) for item in remembered_facts], "\n\n")
    forget_response = ms.forget("The capital of Israel is Jerusalem.", "facts")
