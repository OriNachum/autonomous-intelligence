The server will act as an adapter between the codex client (which expects the Responses API format) and the Ollama service (which uses the chat completions API format).

1. The API adapter needs to be implemented using FastAPI
2. It should convert between Responses API format and chat.completions API format
3. It needs to support streaming responses with proper event handling
4. Any other request should be proxied to the ai provider without a change
5. Tooling will be handled by the codex client, not by the adapter
6. The adapter should run on port 8080 by default
7. The Ollama service runs on port 8000

8. Note this is not a one-to-one conversion. There is a major difference between how responses api trusts events, and chat.completions is polling for them.

Logs:
- Request given and response back.
- Tools related messages
- The summary output collected from the streamed events (The total message)s