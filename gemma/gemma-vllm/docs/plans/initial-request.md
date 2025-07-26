# gemma vllm

I have a jetson-containers docker with vllm in a Jetson device.
Definition in: /home/orin/git/jetson-containers/packages/llm/vllm with Dockerfile, Readme.md, install.sh and more.

I want to write an app around the model gemma 3n e4b (It's a new multimodal model with text, audio and image -> text).

I want to write an app demos running the model with vllm and all its modalities. (Not a chat, just a cli where we input arguments text, audio file, image file and it returns a text)

Model card: https://huggingface.co/google/gemma-3n-E4B

Quant version that supports all modalities: https://huggingface.co/muranAI/gemma-3n-e4b-it-fp16

Example for docker compose with vllm (in comment, it works).

Tech stack: vllm, jetson, docker, docker compose

hugging face secret in .env
