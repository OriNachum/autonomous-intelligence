# Investigation: Graph Agent JSON Decode Error

## Issue Description
The `KnowledgeGraphAgent` encounters a `json.decoder.JSONDecodeError: Expecting value: line 1 column 1 (char 0)` when processing responses from the LLM. 
The log indicates the response length is 5017 characters, which suggests the response is not empty, but rather malformed or contains non-JSON content at the beginning.

## Error Log
```
2026-02-01 20:46:29,999 - graph_agent - DEBUG - Cleaning response (len=5017)
2026-02-01 20:46:30,000 - graph_agent - ERROR - Entity extraction failed: Expecting value: line 1 column 1 (char 0)
Traceback (most recent call last):
  File "/home/spark/git/autonomous-intelligence/qq/agents/graph/graph.py", line 170, in process_messages
    data = json.loads(response_clean)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^
...
json.decoder.JSONDecodeError: Expecting value: line 1 column 1 (char 0)
```

## Root Cause Analysis
The method `_clean_json_response` in `qq/agents/graph/graph.py` uses a fragile cleaning strategy `response.replace("```json", "").replace("```", "").strip()` (conceptually).
Specifically, it checks:
```python
        if response.startswith("```json"):
            response = response[7:]
        elif response.startswith("```"):
            response = response[3:]
```
This fails if the LLM includes conversational text *before* the code block. For example:
```
Here is the extracted data:
```json
{ ... }
```
In this case, `startswith("```json")` is False, and `response.strip()` leaves "Here is the extracted data:..." at the start, which causes `json.loads` to fail immediately with "Expecting value".

## verification
A simple python test confirms that `json.loads` throws exactly this error when parsing a string starting with "Here...":
```python
import json
json.loads("Here is the json: {}")
# json.decoder.JSONDecodeError: Expecting value: line 1 column 1 (char 0)
```

## Recommended Fix
Update `_clean_json_response` to robustly extract the JSON object by searching for the first `{` and the last `}`.

Proposed implementation:
```python
    def _clean_json_response(self, response: str) -> str:
        """Clean LLM response to ensure valid JSON."""
        if not response or not isinstance(response, str):
            logger.warning(f"Empty or non-string response received: {type(response)} {repr(response)}")
            return "{}"

        # Debug logging
        logger.debug(f"Cleaning response (len={len(response)})")
        
        # Find first '{'
        start_idx = response.find('{')
        if start_idx == -1:
             # Fallback or return empty dict if no JSON object found
             logger.warning("No JSON object found in response")
             return "{}"
             
        # Find last '}'
        end_idx = response.rfind('}')
        if end_idx == -1:
             logger.warning("No closing brace found in response")
             return "{}"

        cleaned = response[start_idx:end_idx+1]
        return cleaned
```
This ensures that any conversational prefix or suffix is discarded.
