#!/usr/bin/env python3
"""
Memory Manager for Conversation App

Handles persistent memory storage, loading, and updating using an LLM agent
to extract important facts from conversations.
"""

import json
import logging
import asyncio
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime
import httpx

logger = logging.getLogger(__name__)


class MemoryManager:
    """Manages persistent conversation memory using LLM-based fact extraction."""
    
    def __init__(
        self,
        file_path: str,
        model_name: str,
        api_url: str,
        temperature: float = 0.3
    ):
        """
        Initialize the Memory Manager.
        
        Args:
            file_path: Path to the memory JSON file
            model_name: Name of the LLM model to use for memory updates
            api_url: URL of the LLM API endpoint
            temperature: Temperature for LLM calls (lower = more deterministic)
        """
        self.file_path = Path(file_path)
        self.model_name = model_name
        self.api_url = api_url
        self.temperature = temperature
        
        # Load system prompt for memory agent
        prompt_path = Path(__file__).parent / "agents" / "memory" / "memory_update.system.md"
        self.system_prompt = prompt_path.read_text()
        
        # Current memory cache
        self.current_memory: Dict[str, Any] = {}
        
        logger.info(f"MemoryManager initialized with file: {self.file_path}")
    
    def load_memory(self) -> str:
        """
        Load memory from JSON file.
        
        Returns:
            Formatted string representation of memory for context injection
        """
        try:
            if self.file_path.exists():
                with open(self.file_path, 'r', encoding='utf-8') as f:
                    self.current_memory = json.load(f)
                logger.info(f"✓ Memory loaded from {self.file_path}")
            else:
                # Initialize empty memory structure
                self.current_memory = {
                    "facts": [],
                    "user_profile": {},
                    "conversation_context": {}
                }
                logger.info("No existing memory file, initialized empty memory")
            
            # Format memory for context
            return self._format_memory_for_context(self.current_memory)
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse memory file: {e}")
            # Reset to empty memory if file is corrupted
            self.current_memory = {
                "facts": [],
                "user_profile": {},
                "conversation_context": {}
            }
            return self._format_memory_for_context(self.current_memory)
        except Exception as e:
            logger.error(f"Error loading memory: {e}")
            self.current_memory = {
                "facts": [],
                "user_profile": {},
                "conversation_context": {}
            }
            return self._format_memory_for_context(self.current_memory)
    
    def _format_memory_for_context(self, memory: Dict[str, Any]) -> str:
        """
        Format memory into a human-readable string for context injection.
        
        Args:
            memory: Memory dictionary
            
        Returns:
            Formatted string
        """
        if not memory or not memory.get("facts"):
            return "No previous context available."
        
        context_parts = []
        
        # Add user profile
        user_profile = memory.get("user_profile", {})
        if user_profile.get("name"):
            context_parts.append(f"User's name: {user_profile['name']}")
        if user_profile.get("interests"):
            context_parts.append(f"Interests: {', '.join(user_profile['interests'])}")
        
        # Add important facts by category
        facts = memory.get("facts", [])
        facts_by_category = {}
        for fact in facts:
            category = fact.get("category", "other")
            if category not in facts_by_category:
                facts_by_category[category] = []
            facts_by_category[category].append(f"{fact.get('key')}: {fact.get('value')}")
        
        for category, fact_list in facts_by_category.items():
            if fact_list:
                context_parts.append(f"\n{category.replace('_', ' ').title()}:")
                for fact in fact_list:
                    context_parts.append(f"  - {fact}")
        
        # Add conversation context
        conv_context = memory.get("conversation_context", {})
        if conv_context.get("last_topic"):
            context_parts.append(f"\nLast topic: {conv_context['last_topic']}")
        if conv_context.get("ongoing_tasks"):
            context_parts.append(f"Ongoing tasks: {', '.join(conv_context['ongoing_tasks'])}")
        
        return "\n".join(context_parts)
    
    def save_memory(self, memory_data: Dict[str, Any]) -> bool:
        """
        Save memory to JSON file.
        
        Args:
            memory_data: Memory dictionary to save
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Ensure directory exists
            self.file_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Write memory to file
            with open(self.file_path, 'w', encoding='utf-8') as f:
                json.dump(memory_data, f, indent=2, ensure_ascii=False)
            
            # Update cache
            self.current_memory = memory_data
            
            logger.info(f"✓ Memory saved to {self.file_path}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to save memory: {e}")
            return False
    
    async def update_memory(
        self,
        last_user_message: str,
        last_assistant_response: str
    ) -> Optional[str]:
        """
        Update memory by extracting important facts from the latest interaction.
        
        This method calls the LLM to analyze the conversation and update the memory.
        
        Args:
            last_user_message: The user's last message
            last_assistant_response: The assistant's response
            
        Returns:
            Updated memory as formatted string, or None if update failed
        """
        try:
            # Construct the prompt for the memory agent
            current_memory_json = json.dumps(self.current_memory, indent=2)
            
            user_prompt = f"""**Current Memory:**
```json
{current_memory_json}
```

**New Interaction:**
- User: {last_user_message}
- Assistant: {last_assistant_response}

**Updated Memory:**"""
            
            # Call LLM to update memory
            logger.debug("Calling LLM to update memory...")
            
            messages = [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": user_prompt}
            ]
            
            payload = {
                "model": self.model_name,
                "messages": messages,
                "temperature": self.temperature,
                "max_tokens": 2000,
                "stream": False
            }
            
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(self.api_url, json=payload)
                response.raise_for_status()
                
                result = response.json()
                updated_memory_str = result.get("choices", [{}])[0].get("message", {}).get("content", "")
                
                if not updated_memory_str:
                    logger.warning("LLM returned empty memory update")
                    return None
                
                # Parse the updated memory JSON
                # The LLM should return just JSON, but handle markdown code blocks just in case
                updated_memory_str = updated_memory_str.strip()
                if updated_memory_str.startswith("```json"):
                    updated_memory_str = updated_memory_str[7:]
                if updated_memory_str.startswith("```"):
                    updated_memory_str = updated_memory_str[3:]
                if updated_memory_str.endswith("```"):
                    updated_memory_str = updated_memory_str[:-3]
                updated_memory_str = updated_memory_str.strip()
                
                updated_memory = json.loads(updated_memory_str)
                
                # Save the updated memory
                if self.save_memory(updated_memory):
                    logger.info("✓ Memory updated successfully")
                    return self._format_memory_for_context(updated_memory)
                else:
                    logger.error("Failed to save updated memory")
                    return None
                    
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM memory update as JSON: {e}")
            logger.error(f"LLM response: {updated_memory_str[:200]}...")
            return None
        except httpx.HTTPError as e:
            logger.error(f"HTTP error during memory update: {e}")
            return None
        except Exception as e:
            logger.error(f"Error updating memory: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def get_current_memory_string(self) -> str:
        """
        Get the current memory as a formatted string.
        
        Returns:
            Formatted memory string
        """
        return self._format_memory_for_context(self.current_memory)
