Please implement the following:

# Event System for AI Assistant - Development Plan

## What We're Building
A communication system that lets all parts of the AI (speech, vision, memory, etc.) talk to each other reliably, both on the same device and across the network.

## Key Goals
1. Fast local communication (under 50ms)
2. No message loss for important events
3. Quick recovery if something fails
4. Handle lots of messages smoothly
5. Easy to debug and monitor

## Core Features

### Message System
- Clear message types and priorities
- Know where messages come from and where they're going
- Handle streaming data (audio, video, text)
- Recover from errors automatically

### Local Communication (Unix Sockets)
- Clean up properly when shutting down
- Control who can send/receive
- Handle large streams of data
- Recover if a connection breaks

### Network Communication (WebSockets)
- Secure connections
- Basic security against attacks
- Reconnect automatically if connection drops
- Control message flow

### System Health
- Track what's working/not working
- Recover from failures
- Clean startup/shutdown
- Basic performance tracking

## Implementation Phases

### Phase 1: Core Local System
1. Set up basic message passing
2. Get speech pipeline working
3. Add basic error recovery
4. Add simple monitoring

### Phase 2: Network Layer
1. Add secure connections
2. Set up basic auth
3. Handle reconnections
4. Add remote monitoring

### Phase 3: Improvements
1. Better error handling
2. Performance optimization
3. Add missing features
4. Improve monitoring

## Testing Plan
- Test each component separately
- Test components working together
- Test system under heavy load
- Test recovery from failures
