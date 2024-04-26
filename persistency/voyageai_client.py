import voyageai
from dotenv import load_dotenv
load_dotenv()  # Load environment variables from .env file

vo = voyageai.Client()
# This will automatically use the environment variable VOYAGE_API_KEY.
# Alternatively, you can use vo = voyageai.Client(api_key="<your secret key>")


def embed(text, model, purpose):
	result = vo.embed([text], model=model, input_type=purpose)
	return result.embeddings[0]

def embed_many(texts, model, purpose):
	result = vo.embed(texts, model=model, input_type=purpose)
	return result.embeddings


if "__main__" == __name__:
	embedding = embed("hello world", "voyage-2", "document")
	print(f"result: {embedding[:5]} ({len(embedding)})")
