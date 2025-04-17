# Baby Tau Project with Codex Integration

## Working with Codex

### Option 1: Install Codex on your host machine

1. Make sure you have Node.js and npm installed on your host machine:
   ```bash
   sudo apt update
   sudo apt install -y nodejs npm
   ```

2. Install the Codex CLI globally:
   ```bash
   npm install -g @openai/codex
   ```

3. Set up environment variables to point to your Ollama server:
   ```bash
   export OPENAI_BASE_URL=http://localhost:8000/v1
   export OPENAI_API_KEY=dummy-key
   ```

4. You can now run Codex commands directly on your host:
   ```bash
   codex --help
   ```

### Option 2: Use the Codex container but access it from your host

1. Start the containers:
   ```bash
   docker-compose -f docker-compose-codex.yaml up -d
   ```

2. Set up port forwarding if needed (if not using host network mode):
   ```bash
   ssh -L 8000:localhost:8000 localhost
   ```

3. Create an alias to run codex commands through the container:
   ```bash
   alias docker-codex="docker exec -it codex-assistant-codex-1 codex"
   ```

4. Now you can run commands like:
   ```bash
   docker-codex --help
   ```

### Option 3: Use SSH to access the container directly

1. Start the containers:
   ```bash
   docker-compose -f docker-compose-codex.yaml up -d
   ```

2. SSH into the codex container:
   ```bash
   docker exec -it codex-assistant-codex-1 bash
   ```

3. Run codex commands inside the container:
   ```bash
   codex --help
   ```

## Shared Workspace

The docker-compose setup mounts a `./workspace` directory (configurable via WORKSPACE_DIR in .env) that's shared between your host and the container. You can place files here to access them from either environment.

## API Access

The Ollama API is available at:
- Inside container: http://localhost:8000
- From host: http://localhost:8000 (when using host network mode)

You can test it with:
```bash
curl http://localhost:8000/api/tags
```

