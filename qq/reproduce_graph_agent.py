
import sys
import logging
from pathlib import Path

# Add src to path
sys.path.insert(0, "/home/spark/git/autonomous-intelligence/qq/src")
sys.path.insert(0, "/home/spark/git/autonomous-intelligence/qq/agents")

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("reproduce_graph")

try:
    from graph.graph import KnowledgeGraphAgent
    print("Successfully imported KnowledgeGraphAgent")
except ImportError as e:
    print(f"Failed to import KnowledgeGraphAgent: {e}")
    sys.exit(1)

def test_prompt_formatting():
    agent = KnowledgeGraphAgent()
    
    # Test ENTITY_EXTRACTION formatting
    messages = "Ori is working on QQ."
    try:
        prompt = agent.prompts["ENTITY_EXTRACTION"].format(messages=messages)
        print("ENTITY_EXTRACTION prompt formatted successfully")
        # print(prompt) 
    except KeyError as e:
        print(f"ENTITY_EXTRACTION formatting failed with KeyError: {e}")
        return False
    except Exception as e:
        print(f"ENTITY_EXTRACTION formatting failed with {e}")
        return False

    # Test RELATIONSHIP_EXTRACTION formatting
    entities = '[{"name": "Ori", "type": "Person"}]'
    try:
        prompt = agent.prompts["RELATIONSHIP_EXTRACTION"].format(messages=messages, entities=entities)
        print("RELATIONSHIP_EXTRACTION prompt formatted successfully")
    except KeyError as e:
        print(f"RELATIONSHIP_EXTRACTION formatting failed with KeyError: {e}")
        return False
    except Exception as e:
        print(f"RELATIONSHIP_EXTRACTION formatting failed with {e}")
        return False
        
    return True

if __name__ == "__main__":
    if test_prompt_formatting():
        print("All tests passed!")
    else:
        print("Tests failed!")
        sys.exit(1)
