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
from persistency.history import save_to_history, load_history
from services.prompt_service import load_prompt
from assistants.short_term_memory_saver import get_historical_facts, mark_facts_for_deletion
from services.actions_service import extract_actions, is_action_supported, parse_action, execute_action
from services.response_processor import emit_classified_sentences
#from services.speech_queue import SpeechQueue
from services.memory_service import MemoryService
import asyncio

# Set up logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

logger.info("Starting Tau application")

load_dotenv()  # Load environment variables from .env file
logger.debug("Environment variables loaded")

API_KEY = os.getenv("ANTHROPIC_API_KEY")
HISTORY_FILE = "conversation_history.txt"
SYSTEM_PROMPT_FILE = "prompts/system.md"

if not API_KEY:
    logger.error("ANTHROPIC_API_KEY environment variable is not set.")
    raise ValueError("ANTHROPIC_API_KEY environment variable is not set.")

socket_path = "./sockets/tau_hearing_socket"
sel = selectors.DefaultSelector()

def setup_socket():
    logger.info(f"Setting up socket at {socket_path}")
    if os.path.exists(socket_path):
        os.remove(socket_path)
        logger.debug(f"Removed existing socket file: {socket_path}")

    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.bind(socket_path)
    sock.listen(1)
    sock.setblocking(False)  # Set socket to non-blocking mode
    sel.register(sock, selectors.EVENT_READ, accept)
    logger.info("Socket setup complete")
    return sock

def accept(sock):
    conn, addr = sock.accept()
    logger.info(f"Accepted connection from {addr}")
    sel.register(conn, selectors.EVENT_READ, read)

def read(conn):
    data = conn.recv(1024)
    if data:
        logger.debug(f"Received data: {data.decode('utf-8')[:50]}...")  # Log first 50 chars
        return data.decode('utf-8')
    else:
        logger.info("Connection closed")
        sel.unregister(conn)
        conn.close()
        return None

def get_time_since_last(history):
    logger.debug("Calculating time since last interaction")
    last_entry = history.strip().split("\n")[-1]
    timestamp_match = None
    if "[User]" in last_entry:
        logger.debug("Last entry was from User, no time calculation needed")
        return None
    elif "[Assistant]" in last_entry:
        timestamp_match = re.search(r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})', last_entry)
    if timestamp_match:
        timestamp_str = timestamp_match.group(1)
        last_timestamp_obj = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
        time_since_last = datetime.now() - last_timestamp_obj
        days = time_since_last.days
        seconds = time_since_last.seconds
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        seconds = (seconds % 60)
        time_parts = []
        if days > 0:
            time_parts.append(f"{days} days")
        if hours > 0:
            time_parts.append(f"{hours} hours")
        if minutes > 0:
            time_parts.append(f"{minutes} minutes")
        if seconds > 0 or not time_parts:
            time_parts.append(f"{seconds} seconds")
        time_since = ", ".join(time_parts)
        logger.info(f"Time since last interaction: {time_since}")
        return time_since
    else:
        logger.warning("No timestamp found in last entry")
        return None

def handle_events():
    logger.debug("Handling events")
    while True:
        events = sel.select()
        for key, mask in events:
            callback = key.data
            data = callback(key.fileobj)
            if data:
                logger.debug(f"Received data: {data[:50]}...")  # Log first 50 chars
                if "Speech started" in data:
                    logger.info("Speech started event received. Stopping ongoing speech output.")
                    # Add code here to stop ongoing speech output
                    # For example: speech_queue.stop_current()
                    archive_speech()
        
                    # Now wait for the "Speech stopped" event
                    continue

                elif "Speech stopped" in data:
                    logger.info("Speech stopped event received. Returning input.")
                    # Extract the actual speech content
                    speech_content = data.split("Transcript:", 1)[1].strip()
                    return speech_content  # Return the speech content

                else:
                    logger.debug("Received other event, continuing to listen.")
                    continue  # Continue listening for relevant events
    return None  # This line should never be reached

def archive_speech():
    source_folder = "speech_folder"
    # Create the main archive folder if it doesn't exist
    archive_folder = os.path.join(source_folder, 'archive')
    os.makedirs(archive_folder, exist_ok=True)

    # Create a timestamped subfolder
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    timestamped_folder = os.path.join(archive_folder, timestamp)
    os.makedirs(timestamped_folder, exist_ok=True)

    # Counter for moved files
    moved_files = 0

    # Iterate through all files in the source folder
    for filename in os.listdir(source_folder):
        if filename.lower().endswith('.mp3'):
            source_file = os.path.join(source_folder, filename)
            destination_file = os.path.join(timestamped_folder, filename)
            
            # Move the file
            shutil.move(source_file, destination_file)
            moved_files += 1
            print(f"Moved: {filename}")

    print(f"\nTotal files moved: {moved_files}")
    print(f"Files moved to: {timestamped_folder}")


def main_tau_loop(user_input, vision_event_listener):
    next_prompt = None
    try:
        logger.info(f"Starting main Tau loop with user input {user_input}")
        #speech_queue = SpeechQueue()
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
        model_selector_system_prompt, _ = load_prompt("model-selector")
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
                save_to_history("User", prompt)
                logger.info(f"Saved user prompt to history: {prompt[:50]}...")  # Log first 50 chars
            else:
                prompt = raw_prompt
                save_to_history("User", f"{prompt_prefix} Here is the photo you have taken *Photo redacted due technical reasons*")
                logger.info("Saved photo prompt to history")

        if isinstance(prompt, str):
            wrapped_prompt = f"Please assess the correct model for the following request, wrapped with double '---' lines: \n---\n---\n{prompt} \n---\n---\n Remember to answer only with one of the following models (haiku, sonnet, opus)"
        else:
            wrapped_prompt = "opus"
        logger.debug(f"Wrapped prompt prepared: {wrapped_prompt[:50]}...")  # Log first 50 chars
        last_vision = vision_event_listener.get_last_event()
        prompt = f"*What you see: {last_vision}* This what what the person in front of you says: \"{prompt}\""
        model = "gpt-4o"
        speech_index = 0
        response = ""
        #speech_queue.reset()
        archive_speech()
        logger.info("Generating AI response")
        for text_type, text in emit_classified_sentences(openai.generate_stream_response(prompt, history, tau_system_prompt, model)):
            if (text is not None) and (text_type is not None):
                logger.debug(f"Generated {text_type}: {text[:50]}...")  # Log first 50 chars
                response += text
            if text_type == "speech":
                app_root = Path.cwd()
                path = f"speech_folder/speech_{speech_index}.mp3"
                speech_file_path = app_root / path
                speech_index += 1
                speech_file_path = openai.speechify(text, speech_file_path)
                if (path is not None):
                    #speech_queue.enqueue(path)
                    logger.debug(f"Enqueued speech file: {speech_file_path}")

        save_to_history("Assistant", response)
        logger.info("Saved assistant response to history")

        logger.info("Processing historical facts")
        facts = get_historical_facts()
        facts_string = "\n".join(facts)
        add_to_direct_knowledge(facts_string)
        memory_service.remember_many(facts, "facts")
        deprecated_facts = mark_facts_for_deletion()
        new_facts_string = "\n".join([fact for fact in facts if fact not in deprecated_facts])
        save_over_direct_knowledge(new_facts_string)
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
            archive_speech()

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

def main():
    logger.info("Starting main function")
    sock = setup_socket()
    
    # Initialize EventListener for external events
    gst_socket_path = "/tmp/gst_detection.sock"
    vision_event_listener = EventListener(gst_socket_path, sel, external_event_callback)

    print(f"Listening on {socket_path}")
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
        os.remove(socket_path)
        logger.info("Application shutdown complete")

if __name__ == "__main__":
    main()
