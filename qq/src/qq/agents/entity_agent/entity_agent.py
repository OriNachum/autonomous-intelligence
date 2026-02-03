from strands import Agent
import json
import logging
from pathlib import Path
from typing import List, Dict, Any

from qq.agents.prompt_loader import get_agent_prompts

logger = logging.getLogger("entity_agent")

class EntityAgent:
    """Agent responsible for extracting entities from conversation history."""
    
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

    def extract(self, messages: List[Dict[str, str]]) -> List[Dict[str, Any]]:
        """
        Extract entities from the provided messages.
        
        Args:
            messages: List of message dictionaries containing 'role' and 'content'
            
        Returns:
            List of extracted entities
        """
        if not self.model:
            logger.warning("Model not available, skipping extraction")
            return []

        if not messages:
            return []

        # Load prompts dynamically
        prompts = get_agent_prompts("entity_agent")
        if "user" not in prompts:
            logger.error("Missing user prompt for entity extraction")
            return []

        # Prepare text (last 20 messages)
        recent_messages = messages[-20:]
        combined_text = "\n".join([f"{m['role'].upper()}: {m['content']}" for m in recent_messages])
        response="((Entities agent not run yet))"
        try:
            prompt = prompts["user"].format(messages=combined_text)
            logger.info("Requesting entity extraction from LLM...")
            
            # Create a temporary agent
            agent = Agent(
                name="entity_extractor",
                system_prompt=prompts.get("system", "You are a precise JSON-only assistant."),
                model=self.model
            )
            
            # Get response (strands agent doesn't take temperature in call usually, relies on model config or kwargs)
            # The model configuration handles temperature if possible, looking at __init__.py it is configurable.
            # But the agent call interface is likely agent(text).
            response = str(agent(prompt))
            
            response_clean = self._clean_json_response(response)
            data = json.loads(response_clean)
            entities_list = data.get("entities", [])
            
            logger.info(f"LLM found {len(entities_list)} entities")
            return entities_list
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON response: {e}, prompt: {response}")
            return []
        except Exception as e:
            logger.error(f"Entity extraction failed: {e}, {response}", exc_info=True)
            return []
