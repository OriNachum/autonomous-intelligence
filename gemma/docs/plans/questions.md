# Questions for Gemma Project

## Event System Architecture

1. What Unix domain socket implementation will be used for event management? ***Answer:*** My own implementation. Example in this repo under ../TauLegacy/
2. How will event priorities be handled in the system? ***Answer:*** Latest counts
3. What is the expected event throughput and latency requirements? ***Answer:*** Undecided

## Queue Management

4. What is the maximum queue size for sentences? ***Answer:***  Undecided. Unblocked, but capped by max_tokens  
5. How should the system handle queue overflow scenarios? ***Answer:***  overflow not expected due max_tokens limit
6. What text-to-speech engine will be integrated? KokoroTTS model supported by Jetson-containers

## Camera Processing

7. Which object detection model will be used? ***Answer:***  Yolov6
8. What are the target frame rates for camera processing? ***Answer:***  Undecided
9. How will camera calibration and configuration be handled? ***Answer:***  Irrelevant for now
10. What objects should the detection model prioritize? ***Answer:***  Humans, animals
Note: Last frame will always be sent as well, so the model gets current state + last events of object changes. (Appear/disappear)

## Audio Processing

11. Which VAD (Voice Activity Detection) model will be implemented? ***Answer:***  SileroVAD Supported by Jetson-containers
12. What wake word detection system will be used? ***Answer:***  Gemma or Hey Gemma
13. How will background noise filtering be handled? ***Answer:***  Undecided. Possibly natively by headset
14. What audio quality/sampling rate requirements are needed? ***Answer:***  Undecided

## Model Inference

15. Which language model will be used for inference? ***Answer:*** Gemma 3n - it's image, audio, text -> text model. I will send all 3, all the time.
16. What is the target response time for model inference? ***Answer:*** Time to first word said 400ms. Will be implemented by only running TTS on content between quotations, and prompting the model to split sentences. (So "Hey" *Looking at the user* "Look at me when I am speaking to you") will have 2 sentences, and since I queue speech generation, and speech play in parallel, by the time the first word is said, the next sentence is already finished and ready to play, and so on. This gives the experience of real time. 
17. How will the system prompt be structured? ***Answer:*** Reply in quotations what you want the user to hear - only what is in quotations is sent to the user. Use asterisk for actions. If it can be executed - it will be. (The last part is a preparations for robot performing actions not via tool use, but by play-acting an entity, and having a background system executing the actions.)
18. What is the optimal message history length (X messages)? Let's start with 20 messages.

## Memory Management

19. What criteria determine when facts should be archived from immediate memory? ***Answer:***  Inner model decides what to archive - gemma 3n with the same input, but different instructions. 
20. How will fact importance be scored for distillation? ***Answer:*** Undecided
21. What is the target size for immediate memory? ***Answer:*** 50-100 facts

## Long-term Memory

22. What Milvus configuration and indexing strategy will be used? ***Answer:*** Embeddings from sentence. Embeddings model undecided.
23. How will the Neo4j graph structure be designed? ***Answer:*** Undecided. Possible a model responsible for it.
24. What embedding model will be used for semantic search? ***Answer:*** Undecided. Something Vllm or Ollama support.
25. How will memory relevance scoring work? ***Answer:*** Undecided
26. What triggers the "stop current speech and send again with memory" behavior? ***Answer:***  A small decision model with same input and different prompt.

## Integration and Deployment

27. What hardware requirements are needed for the system? ***Answer:*** Microphone, Speakers, Camera, AGX 64GB Jetson
28. How will the different loops be orchestrated and managed? ***Answer:*** Different applications, possibly on different dockers with shared volumes 
29. What monitoring and logging strategy will be implemented? ***Answer:*** python logger
30. How will the system handle failures in individual components? ***Answer:*** Undecided