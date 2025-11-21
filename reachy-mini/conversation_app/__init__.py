#!/usr/bin/env python3
"""
Conversation Application Package

This package provides a conversation system with speech event integration.

Main components:
- EventHandler: Manages speech events from hearing service
- ConversationParser: Parses LLM responses for speech and actions
- SpeechHandler: Manages TTS output through reSpeaker device
- ConversationApp: Main application orchestrating the conversation flow
"""

from .event_handler import EventHandler
from .conversation_parser import ConversationParser
from .speech_handler import SpeechHandler
from .app import ConversationApp

__all__ = [
    'EventHandler',
    'ConversationParser',
    'SpeechHandler',
    'ConversationApp',
]

__version__ = '1.0.0'
