import os
import socket
import selectors
import re
import logging
import shutil
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
from modelproviders.openai_api_client import OpenAIService
from persistency.direct_knowledge import load_direct_knowledge, add_to_direct_knowledge, save_over_direct_knowledge
from persistency.history import save_to_history, load_history, get_time_since_last
from services.prompt_service import load_prompt
from memory.memory_short_term import get_historical_facts, mark_facts_for_deletion
from memory.memory_service import MemoryService
from action_handler import extract_actions, is_action_supported, parse_action, execute_action
from ai_service import get_model_response

import asyncio
import threading  # Added import

from config import API_KEY, HISTORY_FILE, SYSTEM_PROMPT_FILE, logger
from event_handler import setup_socket, handle_events, sel
#from speech_processing import archive_speech
from services.event_listener import EventListener

logger.info("Initializing log")
memory_context = "facts"
def main_tau_loop(user_input, vision_event_listener):
    next_prompt = None
    try:
        logger.info(f"Starting main Tau loop with user input {user_input}")
        logger.debug("Speech queue loaded")
        memory_service = MemoryService()
        logger.debug("Memory loaded")
        openai = OpenAIService()
        logger.debug("OpenAI service loaded")
        history = load_history()
        logger.debug("History loaded")
        direct_knowledge = load_direct_knowledge()
        logger.debug("Direct knowledge loaded")
        tau_system_prompt, _ = load_prompt("tau")
        tau_system_prompt = tau_system_prompt.replace("{{direct_knowledge}}", direct_knowledge)
        logger.debug("Prompts loaded and prepared")

        logger.info("Processing user input")
        last_entry = history.strip().split("\n")[-1]
        if "[User]" in last_entry:
            prompt = last_entry.split("[User]")[1].strip()
            history = history[:history.rfind("[User]")]
            logger.debug("Using last user entry as prompt")
        else:
            time_since_last = get_time_since_last(history)
            raw_prompt = user_input if user_input is not None else handle_events()
            logger.debug(f"raw prompt is: {raw_prompt}")
            current_datetime = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            if time_since_last:
                time_since_last_str = str(time_since_last).split('.')[0]
                prompt_prefix = f"[{current_datetime}][{time_since_last_str}]"
            else:
                logger.warning("No previous timestamp found in the conversation history.")
                prompt_prefix = f"[{current_datetime}]"
            if isinstance(raw_prompt, str):
                prompt = f"{prompt_prefix} {raw_prompt}"
                threading.Thread(target=save_to_history, args=("User", prompt)).start()
                logger.info(f"Saved user prompt to history: {prompt[:50]}...")  # Log first 50 chars
            else:
                prompt = raw_prompt
                threading.Thread(target=save_to_history, args=("User", f"{prompt_prefix} Here is the photo you have taken *Photo redacted due technical reasons*")).start()
                logger.info("Saved photo prompt to history")
        last_vision = vision_event_listener.get_last_event()
        relevant_memories = memory_service.retrieve_relevant_memories(history, memory_context)
        prompt = f"*As we speak, you recall these bits, thank to your RAG system:\n{relevant_memories}*\n\n *In front of you, this What you see using your AI Camera: {last_vision}*\n\n*And this what you hear, using speech to text* \"{prompt}\""
        model = "gpt-4o"
        speech_index = 0
        response = ""
        #speech_queue.reset()
        #archive_speech()
        logger.info(f"Generating AI response for prompt:\n {prompt}")
        response = get_model_response(prompt, history, tau_system_prompt, model, logger)
        logger.info(f"Assistant Response is:\n{response}\n\n---\n") 
        threading.Thread(target=save_to_history, args=("Assistant", response)).start()
        
        logger.info("Processing historical facts")
        facts = get_historical_facts()
        facts_string = "\n".join(facts)
        threading.Thread(target=lambda: (
            add_to_direct_knowledge(facts_string),
            memory_service.remember_many(facts, memory_context),
            save_over_direct_knowledge("\n".join([fact for fact in facts if fact not in deprecated_facts]))
        )).start()
        logger.debug("Historical facts processed and saved")

        logger.info("Extracting and executing actions")
        automated_prompt = None
        actions_list = extract_actions(response)
        for action in actions_list:
            parsed_action = parse_action(action, [])
            if is_action_supported(parsed_action):
                automated_prompt = execute_action(parsed_action)
                logger.info(f"Executed action: {parsed_action}")
                break

        if automated_prompt is not None:
            next_prompt = automated_prompt
            logger.info("Using automated prompt for next iteration")
        else:
            logger.info("Waiting for audio to finish and next event")
            next_prompt = handle_events()  # Wait for the next event
            logger.debug(f"Next prompt: {next_prompt}")
            
            #speech_queue.clear()
            #archive_speech()

        logger.info("Main Tau loop iteration complete")
    except Exception as e:
        logger.error(f"Error in main_tau_loop: {e}", exc_info=True)
    finally:
        logger.debug("cleanup")
        # Ensure cleanup happens even if an exception occurs
        #speech_queue.clear()
        #sel.unregister(sock)
        #sock.close() #sock is not defined

    return next_prompt

def external_event_callback(event_data):
    """
    Callback function to handle external events from the EventListener.
    
    Args:
        event_data (str): The data received from the external event.
    """
    try:
        logger.info(f"External event received: {event_data}")
        
        # Enqueue the event data for processing in the main loop
        #external_event_queue.put(event_data)
        
        logger.debug("External event enqueued successfully.")
    except Exception as e:
        logger.error(f"Error in external_event_callback: {e}", exc_info=True)


def main():
    logger.info("Starting main function")
    sock = setup_socket()
    
    # Initialize EventListener for external events
    gst_socket_path = "/tmp/gst_detection.sock"
    vision_event_listener = EventListener(gst_socket_path, sel, external_event_callback)
    vision_event_listener.start()
    print(f"Listening on {gst_socket_path}")
    event_data = None
    try:
        while True:
            event_data = main_tau_loop(event_data, vision_event_listener)
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt, shutting down.")
    except Exception as e:
        logger.error(f"An unexpected error occurred: {str(e)}", exc_info=True)
    finally:
        logger.info("Cleaning up resources")
        # Close EventListener
        vision_event_listener.close()

        sel.close()
        os.remove(gst_socket_path)
        logger.info("Application shutdown complete")

if __name__ == "__main__":
    main()
