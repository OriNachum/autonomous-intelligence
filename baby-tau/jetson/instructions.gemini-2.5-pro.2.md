# Gemini 2.5 Pro request
https://gemini.google.com/app/2d0b5b657acaac05

Verify existing images with echo $(autotag package-name)
Can build python container, I chose python:3.12

## User

I'm trying to set up a docker compose for these:
Under jetson-containers repo (submodule) folder ./packages/ 

- speaches:
  - Location: speech/speaches/Dockerfile
  - Internal Port: 8000, overrideable via enironment variable PORT
  - Existing image: dustynv/kokoro-tts:fastapi-r36.4.0-cu128-24.04
- vllm: 
  - Location: llm/vllm/Dockerfile
  - Internal Port: 8000
  - Existing image: dustynv/vllm:0.7.4-r36.4.0-cu128-24.04
- KokoroTTS fastapi
  - Location: speech/kokoro-tts/kokoro-tts-fastapi/Dockerfile/
  - Internal Port: 8880
  - Existing image: dustynv/kokoro-tts:fastapi-r36.4.0-cu128-24.04
- Python
  - Location: build/python/Dockerfile 
  - Existing image: python-3.12:r36.4.3 

**Notes:**
1.  I have a local clone of the `dusty-nv/jetson-containers` repository.
2.  This `docker-compose.yml` file will reside in a directory *outside* the `jetson-containers` clone. For example:
    ```
    my-project/
    ├── docker-compose.yml
    ├── .env
    ├── jetson-containers/  <-- Your clone of the repo
    └── my_app_code/        <-- Directory for your Python application code
        └── main.py         <-- Your script that uses the services
    ```
3.  All services need GPU access on the Jetson device. 
4.  We'll use a `.env` file to manage configurable parameters like ports, base image tag, and model names.
5.  The `vllm` container needs:
- a command to start the API server, which isn't specified in its Dockerfile's `ENTRYPOINT` or `CMD`. We'll add a default command.
- huggingface token to support protected models, like gemma
- configuranle option to limit max memory to avoid full use of the memory for caching
6. No need to build docker images - they are ready according to list above under "Existing image"
7. No `iptable_raw` support -> Use `network mode: host`
8. Use the following shared properties between containers:
```yaml
x-shared-properties: &shared-properties
  runtime: nvidia                 # Use NVIDIA runtime
  init: false                     # Do not use init process
  restart: unless-stopped         # Restart policy
  network_mode: host              # Use host network mode, to auto-detect devices in network
  devices:
    - /dev/snd:/dev/snd           # to share audio devices
    - /dev/bus/usb                # to share usb devices
```

I will use each of the dockers as a server, and python will host my code in python to use the rest.

Can you set up a docker compose up for me?

I use dusty-nv/jetson-containers for all of these dockers
Note I am a maintainer of the repo as well, and can change a Dockerfile if it improves it (For example, if I make it more configurable by adding override to the port, etc.)


## Note
vllm is broken
I had to fix the dockerfile

## Gemini
