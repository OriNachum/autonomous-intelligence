import os
import json
import voyageai

class EmbeddingsManager:
    def __init__(self, embeddings_dir="embeddings"):
        self.embeddings_dir = embeddings_dir
        os.makedirs(self.embeddings_dir, exist_ok=True)
        self.client = voyageai.Client()

    def generate_embeddings(self, text_list, file_name):
        embeddings = self.client.embed(text_list, model="voyage-2")
        file_path = os.path.join(self.embeddings_dir, f"{file_name}.json")
        with open(file_path, "w") as f:
            json.dump(embeddings, f)

        return embeddings

    def find_similar(self, embedding, file_name, top_k=5):
        file_path = os.path.join(self.embeddings_dir, f"{file_name}.json")
        with open(file_path, "r") as f:
            embeddings = json.load(f)

        similarities = []
        for stored_embedding in embeddings:
            similarity = sum(a * b for a, b in zip(embedding, stored_embedding))
            similarities.append(similarity)

        sorted_indices = sorted(range(len(similarities)), key=lambda i: similarities[i], reverse=True)
        top_indices = sorted_indices[:top_k]
        top_similarities = [similarities[i] for i in top_indices]
        top_embeddings = [embeddings[i] for i in top_indices]

        return top_similarities, top_embeddings

def main():
    embeddings_manager = EmbeddingsManager()

    actions = [
        "Open a new file",
        "Save the current file",
        "Copy selected text",
        "Paste copied text",
        "Undo the last action",
        "Redo the last undone action"
    ]

    embeddings = embeddings_manager.generate_embeddings(actions, "actions")

    query_embedding = embeddings[0]
    top_similarities, top_embeddings = embeddings_manager.find_similar(query_embedding, "actions")

    print("Top similar embeddings:")
    for sim, embed in zip(top_similarities, top_embeddings):
        print(f"Similarity: {sim}, Embedding: {embed}")

if __name__ == "__main__":
    main()