"""Graph Linking Agent - finds relationships for orphan entities."""

import json
import logging
from typing import List, Dict, Any

from strands import Agent
from qq.agents.prompt_loader import get_agent_prompts
from qq.knowledge.neo4j_client import Neo4jClient

logger = logging.getLogger("graph_linking_agent")


class GraphLinkingAgent:
    """Agent responsible for finding relationships for disconnected entities."""

    def __init__(self, model: Any, neo4j_client: Neo4jClient):
        self.model = model
        self.neo4j = neo4j_client

    def _clean_json_response(self, response: str) -> str:
        """Clean LLM response to ensure valid JSON."""
        if not response or not isinstance(response, str):
            logger.warning(f"Empty or non-string response received: {type(response)} {repr(response)}")
            return "{}"

        # Remove thinking process if present
        if "</think>" in response:
            response = response.split("</think>")[-1]

        response = response.strip()
        if response.startswith("```json"):
            response = response[7:]
        elif response.startswith("```"):
            response = response[3:]

        if response.endswith("```"):
            response = response[:-3]

        cleaned = response.strip()
        if not cleaned:
            return "{}"

        return cleaned

    def get_orphan_entities(self) -> List[Dict[str, Any]]:
        """Get entities with no relationships."""
        query = """
            MATCH (n)
            WHERE NOT (n)-[]-()
            RETURN n.name as name, labels(n)[0] as type, n.description as description
            LIMIT 50
        """
        try:
            return self.neo4j.execute(query)
        except Exception as e:
            logger.error(f"Failed to get orphan entities: {e}")
            return []

    def get_connected_entities(self, limit: int = 30) -> List[Dict[str, Any]]:
        """Get entities that have relationships."""
        query = """
            MATCH (n)-[r]-()
            WITH n, count(r) as rel_count
            RETURN n.name as name, labels(n)[0] as type, n.description as description, rel_count
            ORDER BY rel_count DESC
            LIMIT $limit
        """
        try:
            return self.neo4j.execute(query, {"limit": limit})
        except Exception as e:
            logger.error(f"Failed to get connected entities: {e}")
            return []

    def link_orphans(self) -> Dict[str, Any]:
        """Find and suggest links for orphan entities."""
        if not self.model:
            logger.warning("Model not available, skipping orphan linking")
            return {"suggested_relationships": []}

        # Get orphan and connected entities
        orphan_entities = self.get_orphan_entities()
        connected_entities = self.get_connected_entities()

        if not orphan_entities:
            logger.info("No orphan entities found")
            return {"suggested_relationships": []}

        # Load prompts dynamically
        prompts = get_agent_prompts("graph_linking_agent")
        if "user" not in prompts:
            logger.error("Missing user prompt for graph linking")
            return {"suggested_relationships": []}

        # Format entities for prompt
        orphan_json = json.dumps(orphan_entities, indent=2)
        connected_json = json.dumps(connected_entities, indent=2)

        try:
            prompt = prompts["user"].format(
                orphan_entities=orphan_json,
                connected_entities=connected_json,
            )

            logger.info(f"Requesting link suggestions for {len(orphan_entities)} orphan entities...")

            # Create a temporary agent
            agent = Agent(
                name="graph_linker",
                system_prompt=prompts.get("system", "You are a precise JSON-only assistant."),
                model=self.model,
            )

            # Get response
            response = str(agent(prompt))

            response_clean = self._clean_json_response(response)
            data = json.loads(response_clean)
            suggestions = data.get("suggested_relationships", [])

            logger.info(f"LLM suggested {len(suggestions)} relationships for orphans")
            return {"suggested_relationships": suggestions}

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON response: {e}")
            return {"suggested_relationships": []}
        except Exception as e:
            logger.error(f"Graph linking failed: {e}", exc_info=True)
            return {"suggested_relationships": []}
