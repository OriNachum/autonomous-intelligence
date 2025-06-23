# Tau - The Autonomous, Understanding robot

This is Tau!  
Tau is inspired by Pi.AI and if you havent tried Pi yet, I strongly encourage you to try.  
Like Pi, Tau's conversation is on continual conversation, unlike Chat based bots which feature many conversations and threads.  
This is by design - Tau has a single conversation, like speaking to a human.  
This is reflected by consulting Tau in decisions made along development: Order of features, voice type, etc.

Tau is a personal fun project.  
I opened it as an open source for anyone to experiment with (fork), or just follow. (A star is appreciated!)  
If you fork - delete history and facts to reset their knowledge and embark the journey anew!  

## Update status

- [x] System Prompt: Speech-actions speak conversation structure.
- [x] Conversation loop: A continueous conversation with ongoing context.
- [x] Immediate memory: Reduce context by summarizing it to key points. Inject memory to System prompt.
- [x] Long term memory: Save the running memory to vector database.
- [x] Speech: Voice based conversation with hearing and speaking. (Whisper and OpenAI TTS)
- [ ] **Vision infra: Set up Hailo-8L as an internal vision webservice.**
  - [x] Setup Hailo-8L on Raspberry Pi, validate examples work.
  - [x] Look for best practices and options for integrating Hailo in your application.
  - [x] Find a suitable, working architecture to wrap hailo as a service
  - [x] Implement and improve the wrapper
  - [ ] **Pending Hailo review** (update, will be integrates as community-examples, confirmed by Hailo)
  - [x] Integrate in the system, allow Tau to recognize faces
  - [ ] add more-than-one models to be used serially, or use different devices (Coral, Sony AI Camera x2, Jetson)
- [x] Long term fetching: Pull from long term memory into context.
- [x] Auto-start on device startup.
- [x] Long term memory archiving support.
- [ ] Entity based memory: Add GraphRAG based memory.
  - [x] Learn about GraphRAG, how to implement, etc.
  - [ ] **Use or implement GraphRAG**
- [x] Design further split to applications, event communications
- [x] Setup Nvidia Jetson Orin Nano Super 8GB
  - [x] Local LLM on Jetson
    - [x] Ollama (Llama 3.2 3:b)
    - [ ] **Move to use jetson-containers**
    - [ ] TensorRT
    - [ ] Transformers
  - [x] *Local Speech to text (faster-whisper) on Jetson*
    - [x] WebRT VAD
    - [x] Silero VAD
  - [x] Implement Text to speech
    - [x] piperTTS
    - [x] kokoroTTS
    - [ ] israwave 
- [ ] Write a setup guide for Nvidia Jetson Orin Nano Super 8GB
- [ ] **Build every component as a single event-based app**
  - [ ] Communication infra with websocket or unix domain socket (Global)
  - [ ] Configuration infra, local configuration per device (Global)
  - [ ] Detect main component, connects the secondary device to main device (Global)
  - [ ] LLM as a service (Jetson)
  - [ ] Speech detection as a service (Jetson)
  - [ ] Speech as a service (Jetson)
  - [ ] Memory as a service (Jetson)
  - [ ] Vision as a service (Raspberry Pi)
  - [ ] Face as a service (Raspberry Pi)
  - [ ] Main loop (Jetson)
- [ ] Integrate Nvidia Jetson Orin Nano Super 8GB
- [ ] Integrate Hailo 10 as inference station (Llama 3.2 3b)
- [ ] Advanced voice: Move to ElevenLabs advanced voices.
- [ ] Tool use
  - [ ] Add frameqork for actions:
  - [ ] Open live camera feed action
  - [ ] Snap a picture
- [ ] Add aec for voice recognition from https://gist.github.com/thewh1teagle/929af1c6b05d5f96ceef01130e758471
- [ ] Introspection: Add Introspection agent for active and background thinking and processing.
- [ ] Growth: Add nightly finetuning, move to smaller model.

### Notes

While this is still my goal, you may see lower progress. 
This is becuase I have moved local AI development and help maintain jetson-containers.  
I still drive lower cost smart AI with personality, and it is easier on Pi and 3rd party models, but a true AI companion must be local AI.  

I also publish under org TeaBranch:
- [open-responses-server](https://github.com/teabranch/open-responses-server) for mcp support on chat-completions (as responses api and chat completions api) and all OpenAI's responses features
- [agentic-developer-mcp](https://github.com/teabranch/agentic-developer-mcp) for an agentic developer served as mcp that can work with other agentic developers, with agents as code.
- [agentic-code-indexer](https://github.com/teabranch/agentic-code-indexer) for indexing code for the agentic-developer-mcp
- [simple-semantic-chunker](https://github.com/teabranch/simple-semantic-chunker) for simple rag over documents

Join our Jetson AI Homelab discord community to talk more 

-nachos

## Prerequisites

Tau should be able to run on any linux with internet, but was tested only on a raspberry pi 5 8GB with official OS 64bit.  
Raspberry AI Kit is needed for vision (Can be disabled in code - configuration support per request/in future) 

### Keys
All needed keys are in .env_sample.  
Copy it to .env and add your keys.  
Currently, the main key is OpenAI (Chat, Speech, Whisper), and VoyageAI + Pinecone is for vectordb

I plan on moving back to Anthropic (3.5 sonnet only)

Groq was used for a fast understand action usecase

## Installation

1. Cloning Git repositories
1.1. Clone this repository to your Raspberry Pi:

```
git clone https://github.com/OriNachum/autonomous-intelligence.git
```

1.2. Clone this repository to your Raspberry Pi:
```
git clone https://github.com/OriNachum/hailo-rpi5-examples.git
```
I have a pending PR to integrate this to main repo.
```
https://github.com/hailo-ai/hailo-rpi5-examples/pull/50
```
If you do, set up the your machine for Hailo-8L chip per Hailo's instructions.


2. Copy .env_sample to .env and add all keys:
- ANTHROPIC_API_KEY: used for Claude based text completion and vision. Currently unused.
- OPENAI_API_KEY: Used for Speech, Whisper, vision and text.
- GROQ_API_KEY: Used for a super quick action understanding, May be replaced with embeddings.
- VOYAGE_API_KEY: VoyageAI is recommended by Anthropic. They offer the best embeddings to date (of when I selected it), and offer a great option for innovators.
- PINECONE_API_KEY: API Key of pinecone. Serverless is a great option.
- PINECONE_DIMENSION: Dimension of the embeddings generated by Voyage. Used for the setup of Pinecone
- PINECONE_INDEX_NAME: Name of the index in Pinecone, for memory

## Usage

There are five programs to run by this order:
1. hailo-rpi5-examples:
  1. basic-pipelines/detection_service.py: This runs the camera and emits events on changes on detection 
2. autonomous-intelligence
  1. services/face_service.py: this starts the face app, and reacts when speech occurs
  2. tau.py: this is the main LLM conversation loop
  3. tau_speech.py: this consumes speech events, and produces actual speech
  4. services/microphone_listener.py this listens to your speech and emits events to tau.py as input

## Acknowledgements

There are multiple people for which I want to acknowledge for this development.  
Of them, these are the people who confirmed for me to mention them: 
- @Sagigamil 
  
## Star History

[![Star History Chart](https://api.star-history.com/svg?repos=OriNachum/autonomous-intelligence&type=Date)](https://www.star-history.com/#OriNachum/autonomous-intelligence&Date)

⸻

## License

This project is licensed under the [MIT License](LICENSE).
