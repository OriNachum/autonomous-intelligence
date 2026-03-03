---
name: deploy
description: Build and deploy the realtime-api Docker container with full verification that deployed code matches local source.
triggers:
  - deploy
  - redeploy
  - rebuild
  - restart container
  - ship it
---

# Deploy Realtime-API

Build, deploy, and verify the realtime-api Docker container.

## When to use

- After making code changes to `src/realtime_api/` files
- When the user says "deploy", "redeploy", "rebuild", "restart"
- After implementing fixes or features that need testing against the live system

## Instructions

Run the deploy script:

```bash
cd /home/spark/git/autonomous-intelligence/realtime-api && bash scripts/deploy.sh
```

The script will:
1. Verify all required source files exist
2. Build the Docker image with `--no-cache` (guarantees fresh copy)
3. Restart only the `realtime-api` container (preserves TTS/STT/LLM)
4. Wait for the container to be running
5. Verify deployed code matches local source (hash comparison + feature checks)
6. Show recent container logs

## After deploying

After a successful deploy, speak a brief confirmation:

```bash
/home/spark/git/autonomous-intelligence/realtime-api/scripts/speak.sh "Deploy complete. All checks passed."
```

## Troubleshooting

- If hash mismatch: Docker build cache may be stale — the script already uses `--no-cache`
- If container won't start: check `docker compose logs realtime-api`
- If dependencies (TTS/STT/LLM) are down: `docker compose up -d` to start all services
