
import os
import sys
from pathlib import Path


if __name__ == "__main__":
    parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if parent_dir not in sys.path:
        sys.path.append(parent_dir)

#from modelproviders.anthropic_api_client import generate_stream_response
from modelproviders.openai_api_client import OpenAIService
from modelproviders.speechify_espeak import SpeechService

def emit_classified_sentences(stream):
    within_asterisk = False
    within_quote = False
    buffer = ""
    for char,_,_ in stream:
        print(char)
        if (char is None):
            continue
        started_within_asterisk = within_asterisk
        started_within_quote = within_quote
        if '*' in char:
            print("found *")
            within_asterisk = not within_asterisk
        elif '"' in char:
            print("found \"")
            within_quote = not within_quote

        if not within_quote:
            if started_within_asterisk and not within_asterisk:
                print(buffer)
                yield "action", f"{buffer}{char}"
                buffer = ""
                    
        if not within_asterisk:
            if started_within_quote and not within_quote:
                print(buffer)
                yield "speech", f"{buffer}{char}"
                buffer = ""
        if within_asterisk or within_quote:
            buffer += char

    # Yield remaining content if any
    if buffer:
        yield None,buffer

def get_model_response(prompt, history, tau_system_prompt, model, logger):
    openai = OpenAIService()
    speech_engine = SpeechService()
    response = ""
    speech_index = 0
    for text_type, text in emit_classified_sentences(openai.generate_stream_response(prompt, history, tau_system_prompt, model)):
        if (text is not None) and (text_type is not None):
            logger.debug(f"Generated {text_type}: {text[:50]}...")  # Log first 50 chars
            response += text
        if text_type == "speech":
            app_root = Path.cwd()
            path = f"speech_folder/speech_{speech_index}.mp3"
            speech_file_path = app_root / path
            speech_index += 1
            speech_file_path = speech_engine.speechify(text, speech_file_path)
            if (path is not None):
                #speech_queue.enqueue(path)
                logger.debug(f"Enqueued speech file: {speech_file_path}")
    return response


# Example usage:
#text_stream = 'This is *some* "text" with *multiple* "sections".'
#for section in validate_text_stream(text_stream):
#    print(section)

if __name__ == "__main__":
    openai = OpenAIService()
    for text_type,text in emit_classified_sentences(openai.generate_stream_response("I wave at the shopkeeper",  [], "You are a dnd dungeon master and you act as a character. You reply only as a character with (* for action and \" for spoken words by your character. Finish one type of message before continuing to the next type. Avoid Asterisk inside quotations or otherwise. Only once of each type of message. Example: *waves* \"Hi there, hello!\"", "gpt-4o-mini")):
        if (text is not None) and (text_type is not None):
            print(f"{text_type}: {text}", flush=True)
    print("\n\n")
    #validate_text_stream(stream)

