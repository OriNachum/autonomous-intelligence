# Gemma

## Plan
1. All events are Unix domain events. Event management module. Raise / consume events.

2. Queue script that reads sentences. It supports `queue sentences` and `reset queue` events. While queue has content:
Read then dequeue. If get `reset queue` - stop current read

3. Camera feed loop - gstreamer camera loop to emit frames events. Includes object detection model.

4. Sound feed loop - microphone loop to emit sound events `speech detected` and `wake word`. Includes VAD and wake up word models to detect relevant sound. Only when speech detected or when wake up word used emit event along with recorded sound.

5. Text loop - when running, if text entered and sent (press enter) 

6. Main loop, accepts events. 

6.1. Model inference:

6.1.1. Send system prompt, history of last X messages and latest cache of image, sound & memory.

6.2. Memory management:

6.2.1. Immediate memory management:

6.2.1.1. When finished generating a response, distill important facts to remember.

6.2.1.2. Then remove old facts that can be archived. Archived facts go to long-term memory.

6.2.1.3. Inject immediate memory to next request.

6.2.2. Long-term memory management:

6.2.2.1. Store long-term memory in local rag milvus and local graphrag neo4j.

6.2.2.2. Fetch long-term Memory loop - when sending new prompt, create embeddings and search semantically in archive. Inject long-term memory to next request.

6.2.2.3. Run model on fetched long-term memory. If relevant, stop current speech and send again with memory.


