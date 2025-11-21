#!/usr/bin/env python3
"""
Conversation Parser Module

This module parses conversation responses from the LLM, extracting:
- Speech content (text in quotes "...")
- Action content (text in **...**)

The parser works token-by-token for streaming responses and maintains queues
for speech and actions.
"""

import logging
from collections import deque
from typing import Optional

logger = logging.getLogger(__name__)


class ConversationParser:
    """Parses conversation responses to extract speech and actions."""
    
    def __init__(self):
        """Initialize the conversation parser."""
        # Queues for parsed content
        self.speech_queue = deque()  # Queue of speech items (text in quotes)
        self.action_queue = deque()  # Queue of action items (text in **)
        
        # Parser state for streaming
        self.current_quote = ""
        self.current_action = ""
        self.in_quote = False
        self.in_action = False
        self._star_count = 0
    
    def reset(self):
        """Reset parser state (call before processing a new response)."""
        self.current_quote = ""
        self.current_action = ""
        self.in_quote = False
        self.in_action = False
        logger.debug("Parser state reset")
    
    def parse_token(self, token: str):
        """
        Parse a token from the streaming response.
        Extracts quotes "..." as speech and *...* as actions.
        
        Special case: If an action in asterisks appears inside quotes,
        we treat it as: "text before" *action* "text after"
        
        Args:
            token: A token/chunk from the streaming LLM response
        """
        for char in token:
            # Handle quote parsing
            if char == '"':
                if self.in_quote:
                    # End of quote - add to speech queue
                    if self.current_quote:
                        self.speech_queue.append(self.current_quote)
                        logger.info(f'🗣️ Speech: "{self.current_quote}"')
                    self.current_quote = ""
                    self.in_quote = False
                else:
                    # Start of quote
                    self.in_quote = True
            elif char == '*':
                # Handle asterisks - can appear inside or outside quotes
                if self.in_action:
                    # Found closing *, end the action
                    if self.current_action:
                        self.action_queue.append(self.current_action)
                        logger.info(f'⚡ Action: *{self.current_action}*')
                    self.current_action = ""
                    self.in_action = False
                    # If we were inside a quote before the action, resume quote parsing
                    # (this happens automatically since in_quote stays True)
                else:
                    # Found opening *, start action
                    # If we're inside a quote, save the current quote first
                    if self.in_quote and self.current_quote:
                        self.speech_queue.append(self.current_quote)
                        logger.info(f'🗣️ Speech: "{self.current_quote}"')
                        self.current_quote = ""
                        # Keep in_quote True to resume quote after action
                    self.in_action = True
            elif self.in_action:
                # Accumulate action content
                self.current_action += char
            elif self.in_quote:
                # Accumulate quote content
                self.current_quote += char
    
    def get_speech(self) -> Optional[str]:
        """
        Get the next speech item from the queue.
        
        Returns:
            The next speech string, or None if queue is empty
        """
        if self.speech_queue:
            return self.speech_queue.popleft()
        return None
    
    def get_action(self) -> Optional[str]:
        """
        Get the next action item from the queue.
        
        Returns:
            The next action string, or None if queue is empty
        """
        if self.action_queue:
            return self.action_queue.popleft()
        return None
    
    def has_speech(self) -> bool:
        """Check if there are speech items in the queue."""
        return len(self.speech_queue) > 0
    
    def has_action(self) -> bool:
        """Check if there are action items in the queue."""
        return len(self.action_queue) > 0
    
    def speech_count(self) -> int:
        """Get the number of speech items in the queue."""
        return len(self.speech_queue)
    
    def action_count(self) -> int:
        """Get the number of action items in the queue."""
        return len(self.action_queue)
    
    def clear_queues(self):
        """Clear both speech and action queues."""
        self.speech_queue.clear()
        self.action_queue.clear()
        logger.debug("Queues cleared")
