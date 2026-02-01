
from gliner import GLiNER
import logging

logging.basicConfig(level=logging.INFO)

text = """
Ori Nachum is working on the QQ project. He is trying to fix the knowledge graph agent.
The project uses Neo4j and Python.
"""

labels = ["Person", "Concept", "Topic", "Location", "Event"]

print(f"Loading model...")
model = GLiNER.from_pretrained("urchade/gliner_medium-v2.1")

print(f"Predicting entities...")
entities = model.predict_entities(text, labels, threshold=0.3)

for entity in entities:
    print(f"{entity['label']}: {entity['text']}")

print(f"Found {len(entities)} entities")
