#!/usr/bin/env python3
"""
Test script for STT-enabled Hearing Event Emitter

This script connects to the hearing event emitter and displays
speech detection events with transcriptions in real-time.

Usage:
    python3 test_stt.py
"""

import socket
import json
import sys
import os

SOCKET_PATH = os.getenv('SOCKET_PATH', '/tmp/reachy_sockets/hearing.sock')

def main():
    """Connect to hearing event emitter and display events"""
    print(f"Connecting to {SOCKET_PATH}...")
    
    # Create Unix socket client
    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    
    try:
        client.connect(SOCKET_PATH)
        print("Connected! Listening for speech events...")
        print("-" * 60)
        
        buffer = ""
        while True:
            # Receive data
            data = client.recv(4096).decode('utf-8')
            if not data:
                print("Connection closed by server")
                break
            
            # Add to buffer and process complete lines
            buffer += data
            while '\n' in buffer:
                line, buffer = buffer.split('\n', 1)
                if line.strip():
                    try:
                        event = json.loads(line)
                        display_event(event)
                    except json.JSONDecodeError as e:
                        print(f"Error decoding JSON: {e}")
    
    except FileNotFoundError:
        print(f"Error: Socket not found at {SOCKET_PATH}")
        print("Make sure the hearing_event_emitter service is running.")
        sys.exit(1)
    except ConnectionRefusedError:
        print(f"Error: Connection refused at {SOCKET_PATH}")
        print("Make sure the hearing_event_emitter service is running.")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nDisconnecting...")
    finally:
        client.close()

def display_event(event):
    """Display event in a readable format"""
    event_type = event.get('type', 'unknown')
    timestamp = event.get('timestamp', '')
    data = event.get('data', {})
    
    if event_type == 'speech_started':
        event_num = data.get('event_number', '?')
        print(f"\n🎤 Speech Started (Event #{event_num})")
        print(f"   Time: {timestamp}")
    
    elif event_type == 'speech_stopped':
        event_num = data.get('event_number', '?')
        duration = data.get('duration', 0)
        transcription = data.get('transcription', '')
        
        print(f"\n🛑 Speech Stopped (Event #{event_num})")
        print(f"   Time: {timestamp}")
        print(f"   Duration: {duration:.2f}s")
        
        if transcription:
            print(f"   📝 Transcription: \"{transcription}\"")
        else:
            print(f"   📝 Transcription: (empty or failed)")
        
        print("-" * 60)
    
    else:
        print(f"\n❓ Unknown Event: {event_type}")
        print(f"   Data: {json.dumps(data, indent=2)}")

if __name__ == "__main__":
    main()
