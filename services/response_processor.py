
import os
import sys

if __name__ == "__main__":
    parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if parent_dir not in sys.path:
        sys.path.append(parent_dir)

from modelproviders.anthropic_api_client import generate_stream_response

def emit_classified_sentences(stream):
    within_asterisk = False
    within_quote = False
    buffer = ""

    for char,_,_ in stream:
        if (char is None):
            continue
        started_within_asterisk = within_asterisk
        started_within_quote = within_quote
        if '*' in char:
            within_asterisk = not within_asterisk
        elif '"' in char:
            within_quote = not within_quote

        if not within_quote:
            if started_within_asterisk and not within_asterisk:
                yield "action", f"{buffer}{char}"
                buffer = ""
                    
        if not within_asterisk:
            if started_within_quote and not within_quote:
                yield "speech", f"{buffer}{char}"
                buffer = ""
        if within_asterisk or within_quote:
            buffer += char

    # Yield remaining content if any
    if buffer:
        yield None,buffer

# Example usage:
#text_stream = 'This is *some* "text" with *multiple* "sections".'
#for section in validate_text_stream(text_stream):
#    print(section)

if __name__ == "__main__":
    for text_type,text in emit_classified_sentences(generate_stream_response("I wave at the shopkeeper",  [], "You are a dnd dungeon master. You reply only as characters with * for action and \" for words. Only once of each type of message.", "haiku")):
        if (text is not None) and (text_type is not None):
            print(f"{text_type}: {text}", flush=True)
    print("\n\n")
    #validate_text_stream(stream)
