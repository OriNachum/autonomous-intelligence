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

## Technical Specifications

### Event System Architecture

1. **Unix Domain Socket Implementation**: My own implementation. Example in this repo under ../TauLegacy/
2. **Event Priorities**: Latest counts
3. **Event Throughput and Latency**: Undecided

### Queue Management

4. **Maximum Queue Size**: Undecided. Unblocked, but capped by max_tokens
5. **Queue Overflow Handling**: overflow not expected due max_tokens limit
6. **Text-to-Speech Engine**: KokoroTTS model supported by Jetson-containers

### Camera Processing

7. **Object Detection Model**: Yolov6
8. **Target Frame Rates**: Undecided
9. **Camera Calibration**: Irrelevant for now
10. **Object Detection Priority**: Humans, animals

*Note: Last frame will always be sent as well, so the model gets current state + last events of object changes. (Appear/disappear)*

### Audio Processing

11. **VAD Model**: SileroVAD Supported by Jetson-containers
12. **Wake Word Detection**: Gemma or Hey Gemma
13. **Background Noise Filtering**: Undecided. Possibly natively by headset
14. **Audio Quality/Sampling Rate**: Undecided

### Model Inference

15. **Language Model**: Gemma 3n - it's image, audio, text -> text model. I will send all 3, all the time.
16. **Target Response Time**: Time to first word said 400ms. Will be implemented by only running TTS on content between quotations, and prompting the model to split sentences. (So "Hey" *Looking at the user* "Look at me when I am speaking to you") will have 2 sentences, and since I queue speech generation, and speech play in parallel, by the time the first word is said, the next sentence is already finished and ready to play, and so on. This gives the experience of real time.
17. **System Prompt Structure**: Reply in quotations what you want the user to hear - only what is in quotations is sent to the user. Use asterisk for actions. If it can be executed - it will be. (The last part is a preparations for robot performing actions not via tool use, but by play-acting an entity, and having a background system executing the actions.)
18. **Message History Length**: Let's start with 20 messages.

### Memory Management

19. **Immediate Memory Archival Criteria**: Inner model decides what to archive - gemma 3n with the same input, but different instructions.
20. **Fact Importance Scoring**: Undecided
21. **Target Immediate Memory Size**: 50-100 facts

### Long-term Memory

22. **Milvus Configuration**: Embeddings from sentence. Embeddings model undecided.
23. **Neo4j Graph Structure**: Undecided. Possible a model responsible for it.
24. **Embedding Model**: Undecided. Something Vllm or Ollama support.
25. **Memory Relevance Scoring**: Undecided
26. **Memory Interrupt Trigger**: A small decision model with same input and different prompt.

### Integration and Deployment

27. **Hardware Requirements**: Microphone, Speakers, Camera, AGX 64GB Jetson
28. **Loop Orchestration**: Different applications, possibly on different dockers with shared volumes
29. **Monitoring and Logging**: python logger
30. **Component Failure Handling**: Undecided


