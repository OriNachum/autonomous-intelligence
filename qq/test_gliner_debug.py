
from gliner import GLiNER
import logging

text = "Ori Nachum is working on the QQ project. He is trying to fix the knowledge graph agent. The project uses Neo4j and Python."
labels = ["person", "organization", "location", "project", "software"]
threshold = 0.3

models = [
    "urchade/gliner_medium-v2.1",
    "urchade/gliner_small-v2.1",
    "urchade/gliner_large-v2.1"
]

for model_name in models:
    print(f"\n=== Model: {model_name} ===")
    try:
        model = GLiNER.from_pretrained(model_name)
        entities = model.predict_entities(text, labels, threshold=threshold)
        for entity in entities:
             print(f"    {entity['label']}: '{entity['text']}' ({entity['score']:.2f})")
    except Exception as e:
        print(f"    Error loading/running {model_name}: {e}")
