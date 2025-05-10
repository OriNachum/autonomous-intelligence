# 🚀 Local-Codex: Your AI Development Companion
Welcome to Local-Codex, the enterprise-ready solution for AI-powered development assistance! This guide will help you get up and running with minimal fuss.

# # 📋 Prerequisites
For Jetson Users Only
If you're working on NVIDIA Jetson hardware:

- Clone the jetson-containers repository (if not already installed):
```
git clone https://github.com/dusty-nv/jetson-containers
```
- This provides the necessary image for running on Jetson platforms
- Skip this step if not using Jetson hardware

## 🔌 API Compatibility
Local-Codex works with any Chat Completions API provider:
- ✅ Ollama (default in our docker setup)
- ✅ vLLM
- ✅ OpenAI
- ✅ Groq
- ✅ Any other Chat Completions API compatible service
Choose what works best for your home or organization's needs!

## 🐳 Docker Setup
Our Docker Compose includes two containers:
- Ollama Container: Runs the LLM service
  - Can be replaced with any other Chat Completions API
  - Skip this container if using an external API
- Python Container: Core application
  - Installs Local-Codex
  - Installs ORS (OpenAI Responses Server)
  - ORS adapts Chat Completions API to Responses API format

## 💻 Local Installation (Recommended)
For the best experience, we recommend installing locally:

## 🌟 Ready to Go!
Once installed, you're all set to supercharge your development workflow!

Happy coding! 💪

