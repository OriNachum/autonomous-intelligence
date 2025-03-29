# my_app_code/main.py

import os
import requests
import json
import time

# --- Configuration (Read from Environment Variables set by Docker Compose) ---
# Use localhost as services are accessible via host network
VLLM_HOST = os.getenv("VLLM_HOST", "localhost")
VLLM_PORT = os.getenv("VLLM_HOST_PORT", "8000") # Get port from .env via compose
VLLM_MODEL_NAME = os.getenv("VLLM_MODEL", "facebook/opt-125m") # Get model used by vLLM service

SPEACHES_HOST = os.getenv("SPEACHES_HOST", "localhost")
SPEACHES_PORT = os.getenv("SPEACHES_HOST_PORT", "8001") # Get port from .env via compose

KOKORO_TTS_HOST = os.getenv("KOKORO_TTS_HOST", "localhost")
KOKORO_TTS_PORT = os.getenv("KOKORO_TTS_HOST_PORT", "8880") # Get port from .env via compose

VLLM_API_URL = f"http://{VLLM_HOST}:{VLLM_PORT}/v1/chat/completions"

# !!! IMPORTANT: Verify the exact API endpoint for kokoro-tts-fastapi !!!
# Assuming '/synthesize' based on common patterns. Check jetson-containers documentation if this fails.
SPEACHES_API_URL = f"http://{SPEACHES_HOST}:{SPEACHES_PORT}/synthesize"
KOKORO_TTS_API_URL = f"http://{KOKORO_TTS_HOST}:{KOKORO_TTS_PORT}/synthesize"

# Output directory within the container (maps to host's ./my_app_code/output)
OUTPUT_DIR = "/app/output"

# --- Helper Functions ---

def ensure_output_dir():
    """Creates the output directory if it doesn't exist."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    print(f"[Setup] Ensured output directory exists: {OUTPUT_DIR}")

def wait_for_service(url: str, service_name: str, timeout: int = 60):
    """Waits for a service to become available by pinging its root or health endpoint."""
    print(f"[Check] Waiting for {service_name} at {url}...")
    start_time = time.time()
    # Try base URL first, then common health endpoints
    check_urls = [url.replace('/synthesize','').replace('/v1/chat/completions',''), f"{url.split('/')[0]}//{url.split('/')[2]}/health", url]

    connected = False
    while time.time() - start_time < timeout:
        for check_url in check_urls:
             # Skip specific API endpoints if they are likely to 404 on GET
             if '/synthesize' in check_url or '/completions' in check_url:
                 continue
             try:
                # Use a simple GET request, often works for root or health checks
                response = requests.get(check_url, timeout=5)
                 # Consider status codes other than 200 OK if needed (e.g., 404 on root might still mean server is up)
                if response.status_code < 500: # Any non-server-error response
                    print(f"[Check] {service_name} is up! (Checked {check_url})")
                    connected = True
                    break
             except requests.exceptions.ConnectionError:
                pass # Service not yet reachable
             except requests.exceptions.Timeout:
                 print(f"[Check] Timeout connecting to {check_url}")
             except Exception as e:
                 print(f"[Check] Error checking {check_url}: {e}") # Log other errors

        if connected:
            return True

        print(f"[Check] {service_name} not responding yet, retrying...")
        time.sleep(5)

    print(f"[Check] Error: {service_name} did not become available within {timeout} seconds.")
    return False


def get_llm_response(prompt: str) -> str | None:
    """Sends prompt to VLLM service and returns the text response."""
    print(f"\n[LLM] Sending prompt to VLLM ({VLLM_API_URL}). Model: '{VLLM_MODEL_NAME}' Prompt: '{prompt}'")
    headers = {"Content-Type": "application/json"}
    payload = {
        "model": VLLM_MODEL_NAME, # vLLM uses this to route if multiple models were loaded
        "messages": [
            {"role": "system", "content": "You are a helpful assistant providing concise answers."},
            {"role": "user", "content": prompt}
        ],
        "max_tokens": 100, # Limit response length
        "temperature": 0.7,
    }
    try:
        response = requests.post(VLLM_API_URL, headers=headers, json=payload, timeout=90) # Increased timeout for generation
        response.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)

        result = response.json()
        generated_text = result.get("choices", [{}])[0].get("message", {}).get("content", "").strip()

        if generated_text:
            print(f"[LLM] Received response: '{generated_text}'")
            return generated_text
        else:
            print("[LLM] Error: Received empty text in response.")
            print(f"[LLM] Full response: {result}")
            return None

    except requests.exceptions.RequestException as e:
        print(f"[LLM] Error connecting to VLLM service: {e}")
        return None
    except json.JSONDecodeError:
        print(f"[LLM] Error decoding JSON response: {response.text}")
        return None
    except Exception as e:
        print(f"[LLM] An unexpected error occurred: {e}")
        return None


def synthesize_speech(text: str, service_name: str, api_url: str) -> bytes | None:
    """Sends text to a TTS service and returns audio bytes."""
    print(f"\n[{service_name}] Synthesizing speech ({api_url}) for: '{text[:60]}...'")
    headers = {"Content-Type": "application/json", "Accept": "audio/wav"} # Request WAV audio
    # Check kokoro-tts docs for exact payload. Common is {"text": "..."}. Voice selection might be possible.
    payload = {"text": text}
    try:
        response = requests.post(api_url, headers=headers, json=payload, timeout=45) # Timeout for synthesis
        response.raise_for_status()

        content_type = response.headers.get("Content-Type", "").lower()
        if "audio" in content_type:
            print(f"[{service_name}] Received audio data ({len(response.content)} bytes, type: {content_type}).")
            return response.content
        else:
            print(f"[{service_name}] Error: Expected audio response, but got Content-Type: {content_type}")
            print(f"Response text: {response.text[:200]}")
            return None

    except requests.exceptions.RequestException as e:
        print(f"[{service_name}] Error connecting to TTS service: {e}")
        return None
    except Exception as e:
        print(f"[{service_name}] An unexpected error occurred: {e}")
        return None

def save_audio(audio_data: bytes, filename: str):
    """Saves audio bytes to a file in the output directory."""
    filepath = os.path.join(OUTPUT_DIR, filename)
    try:
        with open(filepath, 'wb') as f:
            f.write(audio_data)
        print(f"[File] Saved audio to: {filepath} (Host path: ./my_app_code/output/{filename})")
    except IOError as e:
        print(f"[File] Error saving audio to {filepath}: {e}")


# --- Main Application Logic ---
if __name__ == "__main__":
    ensure_output_dir()
    print("\n--- LLM + TTS Demo Application ---")
    print(f"VLLM Endpoint: {VLLM_API_URL} (Model: {VLLM_MODEL_NAME})")
    print(f"Speaches TTS Endpoint: {SPEACHES_API_URL}")
    print(f"Kokoro TTS Endpoint: {KOKORO_TTS_API_URL}")
    print("-" * 30)

    # Wait for services to be potentially ready
    services_ready = True
    if not wait_for_service(VLLM_API_URL, "VLLM"): services_ready = False
    if not wait_for_service(SPEACHES_API_URL, "Speaches TTS"): services_ready = False
    if not wait_for_service(KOKORO_TTS_API_URL, "Kokoro TTS"): services_ready = False

    if not services_ready:
        print("\nOne or more services failed to start. Please check 'docker compose logs'. Exiting.")
        exit(1)

    print("-" * 30)

    try:
        # 1. Get user input
        user_prompt = input("\nEnter a prompt for the LLM (e.g., 'Why is the sky blue?'):\n> ")
        if not user_prompt:
            print("No prompt entered. Exiting.")
            exit()

        # 2. Get response from LLM
        llm_text = get_llm_response(user_prompt)

        if llm_text:
            # 3. Synthesize speech using Speaches service
            speaches_audio = synthesize_speech(llm_text, "Speaches", SPEACHES_API_URL)
            if speaches_audio:
                save_audio(speaches_audio, "output_speaches.wav")

            # 4. Synthesize speech using Kokoro TTS service
            kokoro_audio = synthesize_speech(llm_text, "KokoroTTS", KOKORO_TTS_API_URL)
            if kokoro_audio:
                save_audio(kokoro_audio, "output_kokoro.wav")
        else:
            print("\nCould not get a response from the LLM. Cannot proceed with TTS.")

    except KeyboardInterrupt:
        print("\nExiting application.")
    finally:
        print("\n--- Demo Finished ---")