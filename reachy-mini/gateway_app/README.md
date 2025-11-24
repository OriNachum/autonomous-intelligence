# Reachy Gateway Service

The Reachy Gateway service combines the Reachy Mini daemon (output) and the hearing event emitter (input) into a single unified service that manages both input and output for the Reachy robot.

## Architecture

The gateway service consists of two components running in a single container:

1. **Reachy Mini Daemon** - Provides HTTP API access to robot control (output)
2. **Hearing Event Emitter** - Listens to audio input and emits speech events via Unix socket (input)

## Features

- **Unified Service**: Single service managing both robot input and output
- **Graceful Shutdown**: Properly handles SIGTERM/SIGINT signals to cleanly shutdown both components
- **Startup Scripts**: Automated startup sequence ensuring daemon is ready before hearing service starts
- **Health Checks**: Docker healthcheck monitors both daemon API and hearing socket

## Usage

### Via Docker Compose

```bash
docker-compose up reachy-gateway
```

### Manual Startup

```bash
./gateway_app/start_gateway.sh
```

### Manual Shutdown

```bash
./gateway_app/shutdown_gateway.sh
```

## Environment Variables

- `AUDIO_DEVICE_NAME` - Audio device name (default: "Reachy")
- `LANGUAGE` - Language code for speech recognition (default: "en")
- `SOCKET_PATH` - Unix socket path for hearing events (default: "/tmp/reachy_sockets/hearing.sock")
- See `hearing_app/.env.example` for additional hearing configuration options

## Shutdown Sequence

When shutdown is triggered (Ctrl+C or SIGTERM):

1. Signal handler catches the signal
2. Hearing event emitter is stopped first (SIGTERM → 5s wait → SIGKILL if needed)
3. Reachy daemon is stopped second (SIGTERM → 10s wait → SIGKILL if needed)
4. Container exits cleanly

## Dependencies

The gateway service depends on:
- USB audio devices (for hearing)
- USB devices (for robot connection)
- Shared socket directory at `/tmp/reachy_sockets`

## Files

- `start_gateway.sh` - Startup script with signal handling
- `shutdown_gateway.sh` - Graceful shutdown script
- `requirements.txt` - Python dependencies (merged from daemon + hearing)
