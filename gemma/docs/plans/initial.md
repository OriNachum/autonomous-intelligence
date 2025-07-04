# Gemma

## Plan

1. All events are Unix domain events. Event management module. Raise / consume events.

2. Queue script that reads sentences. It supports `queue sentences` and `reset queue` events. While queue has content:
   Read then dequeue. If get `reset queue` - stop current read

3. Camera feed loop - gstreamer camera loop to emit frames events. Includes object detection model.

4. Sound feed loop - microphone loop to emit sound events `speech detected` and `wake word`. Includes VAD and wake up word models to detect relevant sound. Only when speech detected or when wake up word used emit event along with recorded sound.

5. Text loop - when running, if text entered and sent (press enter) 

6. Main loop, accepts events. 

   - Model inference:
     - Send system prompt, history of last X messages and latest cache of image, sound & memory.

   - Memory management:
     - Immediate memory management:
       - When finished generating a response, distill important facts to remember.
       - Then remove old facts that can be archived. Archived facts go to long-term memory.
       - Inject immediate memory to next request.

     - Long-term memory management:
       - Store long-term memory in local rag milvus and local graphrag neo4j.
       - Fetch long-term Memory loop - when sending new prompt, create embeddings and search semantically in archive. Inject long-term memory to next request.
       - Run model on fetched long-term memory. If relevant, stop current speech and send again with memory.


