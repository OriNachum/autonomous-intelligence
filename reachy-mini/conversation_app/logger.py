#!/usr/bin/env python3
"""
Conversation Audit Logger

This module provides structured logging for conversation audits.
Logs are written in JSONL format to daily log files.
"""

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
import threading

logger = logging.getLogger(__name__)


class ConversationLogger:
    """Singleton logger for conversation audit trails in JSONL format."""
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    # Initialize critical attributes immediately to prevent race conditions
                    cls._instance._write_lock = threading.Lock()
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        """Initialize the conversation logger."""
        # Prevent re-initialization
        if self._initialized:
            return
        
        # Use write lock to ensure thread-safe initialization
        with self._write_lock:
            # Double-check after acquiring lock
            if self._initialized:
                return
            
            # Use /app/logs in production (Docker), logs in current directory for development
            if os.path.exists("/app"):
                self.log_dir = Path("/app/logs")
            else:
                # Use logs directory relative to project root
                project_root = Path(__file__).parent.parent
                self.log_dir = project_root / "logs"
            
            self.log_dir.mkdir(parents=True, exist_ok=True)
            
            # Mark as initialized
            self._initialized = True
            
            logger.info(f"ConversationLogger initialized. Log directory: {self.log_dir}")
    
    def _get_log_file_path(self) -> Path:
        """Get the current day's log file path."""
        date_str = datetime.now().strftime("%Y-%m-%d")
        return self.log_dir / f"conversation_audit_{date_str}.jsonl"
    
    def _write_log(self, event_type: str, data: Dict[str, Any], event_id: Optional[str] = None):
        """
        Write a log entry to the JSONL file.
        
        Args:
            event_type: Type of event being logged
            data: Event-specific data
            event_id: Optional event ID for correlating related events
        """
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "event_type": event_type,
            "data": data
        }
        
        if event_id:
            log_entry["event_id"] = event_id
        
        try:
            with self._write_lock:
                log_file = self._get_log_file_path()
                with open(log_file, 'a') as f:
                    f.write(json.dumps(log_entry) + '\n')
        except Exception as e:
            logger.error(f"Failed to write audit log: {e}", exc_info=True)
    
    # Speech Recording Events
    
    def log_speech_recording_started(self, event_number: int):
        """Log when speech recording starts."""
        self._write_log("speech_recording_started", {
            "event_number": event_number
        })
    
    def log_speech_recording_finished(self, event_number: int, duration: float, samples: int):
        """Log when speech recording finishes."""
        self._write_log("speech_recording_finished", {
            "event_number": event_number,
            "duration": duration,
            "samples": samples
        })
    
    # Transcription Events
    
    def log_transcription_started(self, event_number: int, audio_size: int):
        """Log when transcription starts."""
        self._write_log("transcription_started", {
            "event_number": event_number,
            "audio_size": audio_size
        })
    
    def log_transcription_finished(self, event_number: int, text: str, latency_ms: float):
        """Log when transcription finishes."""
        self._write_log("transcription_finished", {
            "event_number": event_number,
            "text": text,
            "latency_ms": latency_ms
        })
    
    # Model Request/Response Events
    
    def log_model_request_sent(self, messages: List[Dict[str, Any]], parameters: Optional[Dict[str, Any]] = None):
        """Log when a request is sent to the model."""
        self._write_log("model_request_sent", {
            "messages": messages,
            "parameters": parameters or {}
        })
    
    def log_model_response_started(self):
        """Log when model response streaming starts."""
        self._write_log("model_response_started", {})
    
    def log_model_response_finished(self, full_text: str, latency_ms: float):
        """Log when model response is complete."""
        self._write_log("model_response_finished", {
            "full_text": full_text,
            "latency_ms": latency_ms
        })
    
    # Parser Events
    
    def log_parser_cut(self, cut_type: str, content: str):
        """
        Log when parser creates a cut (speech or action).
        
        Args:
            cut_type: Type of cut ('speech' or 'action')
            content: Content of the cut
        """
        self._write_log("parser_cut", {
            "type": cut_type,
            "content": content
        })
    
    # TTS Events
    
    def log_tts_request_queued(self, text: str):
        """Log when TTS request is queued."""
        self._write_log("tts_request_queued", {
            "text": text
        })
    
    def log_tts_started(self, text: str, audio_file: str):
        """Log when TTS playback starts."""
        self._write_log("tts_started", {
            "text": text,
            "audio_file": audio_file
        })
    
    def log_tts_finished(self, text: str, duration_ms: float):
        """Log when TTS playback finishes."""
        self._write_log("tts_finished", {
            "text": text,
            "duration_ms": duration_ms
        })
    
    # Action Handler Events
    
    def log_action_received(self, action_string: str):
        """Log when an action is received by the action handler."""
        self._write_log("action_received", {
            "action_string": action_string
        })
    
    def log_action_llm_request(self, prompt: str, current_state: Optional[Dict[str, Any]] = None):
        """Log when sending action to LLM for parsing."""
        self._write_log("action_llm_request", {
            "prompt": prompt,
            "current_state": current_state
        })
    
    def log_action_llm_response(self, response: str, parsed_commands: List[Dict[str, Any]]):
        """Log when receiving parsed action from LLM."""
        self._write_log("action_llm_response", {
            "response": response,
            "parsed_commands": parsed_commands
        })
    
    # Command Execution Events
    
    def log_command_started(self, command: str, parameters: Dict[str, Any], state_before: Optional[Dict[str, Any]] = None):
        """Log when a command execution starts."""
        self._write_log("command_started", {
            "command": command,
            "parameters": parameters,
            "state_before": state_before
        })
    
    def log_command_finished(self, command: str, state_after: Optional[Dict[str, Any]] = None, 
                            success: bool = True, error: Optional[str] = None):
        """Log when a command execution finishes."""
        self._write_log("command_finished", {
            "command": command,
            "state_after": state_after,
            "success": success,
            "error": error
        })


# Singleton instance accessor
def get_logger() -> ConversationLogger:
    """Get the singleton ConversationLogger instance."""
    return ConversationLogger()
