"""Normalization Agent - normalizes entity names and detects duplicates."""

import json
import logging
from typing import List, Dict, Any

from strands import Agent
from qq.agents.prompt_loader import get_agent_prompts

logger = logging.getLogger("normalization_agent")


class NormalizationAgent:
    """Agent responsible for normalizing entity names and detecting duplicates."""

    def __init__(self, model: Any):
        self.model = model

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

    def normalize(
        self,
        entities: List[Dict[str, Any]],
        existing_entities: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        Normalize entity names via LLM.

        Args:
            entities: List of newly extracted entities
            existing_entities: List of entities already in the graph

        Returns:
            List of normalized entities with canonical_name, aliases, potential_duplicate
        """
        if not self.model:
            logger.warning("Model not available, returning entities unchanged")
            return entities

        if not entities:
            return []

        # Load prompts dynamically
        prompts = get_agent_prompts("normalization_agent")
        if "user" not in prompts:
            logger.error("Missing user prompt for normalization")
            return entities

        # Format entities for prompt
        new_entities_json = json.dumps(entities, indent=2)
        existing_entities_json = json.dumps(existing_entities[:50], indent=2)  # Limit to 50

        try:
            prompt = prompts["user"].format(
                new_entities=new_entities_json,
                existing_entities=existing_entities_json,
            )

            logger.info("Requesting entity normalization from LLM...")

            # Create a temporary agent
            agent = Agent(
                name="entity_normalizer",
                system_prompt=prompts.get("system", "You are a precise JSON-only assistant."),
                model=self.model,
            )

            # Get response
            response = str(agent(prompt))

            response_clean = self._clean_json_response(response)
            data = json.loads(response_clean)
            normalized = data.get("normalized", [])

            logger.info(f"LLM normalized {len(normalized)} entities")

            # Merge normalized data back into original entities
            result = []
            normalized_by_name = {n.get("original_name"): n for n in normalized}

            for entity in entities:
                name = entity.get("name", "")
                if name in normalized_by_name:
                    norm = normalized_by_name[name]
                    # Merge normalized fields into entity
                    entity["canonical_name"] = norm.get("canonical_name", name)
                    entity["aliases"] = norm.get("aliases", [])
                    entity["potential_duplicate"] = norm.get("potential_duplicate")
                    entity["merge_confidence"] = norm.get("merge_confidence", 0.0)
                    # Preserve confidence from normalization if available
                    if "confidence" in norm:
                        entity["confidence"] = norm["confidence"]
                result.append(entity)

            return result

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON response: {e}")
            return entities
        except Exception as e:
            logger.error(f"Normalization failed: {e}", exc_info=True)
            return entities
