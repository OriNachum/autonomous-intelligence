To convert the handling of streamed tool use events from the Chat Completions API to the Responses API, you need to shift from parsing fragmented `delta` chunks to processing structured semantic events.[1]

Here's a breakdown of the conversion process:

1.  **Understand the Chat Completions Streaming Approach:**
    *   When using `stream=True` with tool calls in the Chat Completions API, the response stream consists of JSON chunks.[2, 3, 4, 5]
    *   You iterate through these chunks and check the `chunk.choices.delta.tool_calls` field.[6, 7]
    *   A single tool call (including its `id`, `function.name`, and `function.arguments`) can be split across multiple `delta` objects in consecutive chunks.[6, 7]
    *   You must use the `index` field within each `tool_call` delta to correctly group fragments belonging to the same tool call, especially if multiple tools are called in parallel.[6, 7]
    *   This requires implementing stateful logic on the client-side (e.g., using a dictionary keyed by the `index`) to accumulate the `id`, `name`, and argument fragments until each tool call definition is complete.[6, 7]

2.  **Understand the Responses API Semantic Event Approach:**
    *   The Responses API, when `stream=True`, emits a stream of typed semantic events.[1, 8] Each event has a `type` property indicating its purpose (e.g., `response.output_text.delta`).[1, 8]
    *   Instead of manually assembling tool calls from generic deltas, you listen for specific event types related to tool calls.[1, 8]
    *   While the exact event names should be confirmed with the latest API reference [9, 10], the expected pattern (based on SDK helpers and documentation [8, 11]) involves events such as:
        *   `response.tool_call.created` (Illustrative): Signals the start of a tool call, likely providing the `call_id` and `name`.
        *   `response.tool_call.delta` (Illustrative): Streams fragments of the arguments for a specific `call_id`.
        *   `response.tool_call.done` (Illustrative): Indicates that the definition for a specific tool call (identified by `call_id`) is complete.

3.  **Perform the Conversion:**
    *   **Change Iteration:** Modify your stream processing loop from iterating over `chunks` to iterating over `events`.
    *   **Replace Delta Parsing with Event Handling:** Remove the complex logic that parses `chunk.choices.delta.tool_calls` and uses the `index` to assemble fragments.[6, 7]
    *   **Implement Event Listeners:** Add conditional logic (e.g., `if event.type == 'response.tool_call.created':...`) to handle the specific tool-related semantic events emitted by the Responses API.
    *   **Extract Information Directly:** Within these event handlers, extract the necessary information (like `call_id`, `name`, argument fragments) directly from the properties of the structured event object provided by the API/SDK. The API handles the complexity of associating fragments, presenting you with more complete information tied to a specific `call_id`.

In essence, the conversion involves replacing your manual, stateful fragment assembly code (required for Chat Completions deltas) with simpler, event-driven handlers that react to the explicit, typed tool call events provided by the Responses API's stream.[1] This significantly simplifies the client-side logic needed to handle streamed tool calls.