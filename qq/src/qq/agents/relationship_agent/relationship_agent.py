import json
from strands import Agent
import logging
from pathlib import Path
from typing import List, Dict, Any

from qq.agents.prompt_loader import get_agent_prompts

logger = logging.getLogger("relationship_agent")

class RelationshipAgent:
    """Agent responsible for extracting relationships between entities from conversation history."""
    
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

    def extract(self, messages: List[Dict[str, str]], entities: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Extract relationships from the provided messages and identified entities.
        
        Args:
            messages: List of message dictionaries
            entities: List of entity dictionaries
            
        Returns:
            List of extracted relationships
        """
        if not self.model:
            logger.warning("Model not available, skipping relationship extraction")
            return []

        if not messages:
            return []
            
        if not entities:
            logger.info("No entities provided, skipping relationship extraction")
            return []

        # Prepare text (last 20 messages)
        recent_messages = messages[-20:]
        combined_text = "\n".join([f"{m['role'].upper()}: {m['content']}" for m in recent_messages])
        
        formatted_entities = json.dumps([{"name": e["name"], "type": e["type"]} for e in entities], indent=2)
        
        # Load prompts dynamically
        prompts = get_agent_prompts("relationship_agent")
        if "user" not in prompts:
            logger.error("Missing user prompt for relationship extraction")
            return []

        try:
            prompt = prompts["user"].format(
                messages=combined_text,
                entities=formatted_entities
            )
            
            logger.info("Requesting relationship extraction from LLM...")
            
            # Create a temporary agent
            agent = Agent(
                name="relationship_extractor",
                system_prompt=prompts.get("system", "You are a precise JSON-only assistant."),
                model=self.model
            )
            
            # Get response
            response = str(agent(prompt))
            
            response_clean = self._clean_json_response(response)
            data = json.loads(response_clean)
            relationships = data.get("relationships", [])
            
            logger.info(f"LLM found {len(relationships)} relationships")
            return relationships
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON response: {e}")
            return []
        except Exception as e:
            logger.error(f"Relationship extraction failed: {e}", exc_info=True)
            return []
