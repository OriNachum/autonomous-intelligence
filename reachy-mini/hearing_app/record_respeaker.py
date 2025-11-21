#!/usr/bin/env python3
"""
Record ReSpeaker Microphone for 10 seconds

This script records audio from a ReSpeaker microphone for a specified duration
and saves it to a WAV file.

Usage:
    python3 record_respeaker.py [--duration SECONDS] [--device DEVICE_NAME] [--output FILENAME]

Examples:
    python3 record_respeaker.py                           # Record 10 seconds to 'recording.wav'
    python3 record_respeaker.py --duration 5              # Record 5 seconds
    python3 record_respeaker.py --device ReSpeaker        # Specify device explicitly
    python3 record_respeaker.py --output my_recording.wav # Custom output file
    python3 record_respeaker.py --list-devices            # List available audio devices
"""

import pyaudio
import wave
import sys
import logging
import argparse
import time
from pathlib import Path

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class ReSpeakerRecorder:
    """Record audio from ReSpeaker microphone"""
    
    def __init__(self, device_name='reachy', duration=10, output_file='recording.wav'):
        """
        Initialize ReSpeaker recorder
        
        Args:
            device_name: Name of the audio device to use
            duration: Recording duration in seconds
            output_file: Output WAV file path
        """
        self.device_name = device_name.lower()
        self.duration = duration
        self.output_file = output_file
        
        # Audio configuration
        self.sample_rate = 16000
        self.chunk_size = 8192  # Even larger chunks for better performance
        self.channels = 2  # ReSpeaker has 2 channels
        self.format = pyaudio.paInt16
        
        # PyAudio instance
        self.p = None
        self.stream = None
        self.device_index = None
    
    def find_device(self):
        """Find audio device by name"""
        logger.info(f"Searching for audio device: {self.device_name}")
        
        self.p = pyaudio.PyAudio()
        device_count = self.p.get_device_count()
        logger.info(f"Found {device_count} audio devices")
        
        for i in range(device_count):
            device_info = self.p.get_device_info_by_index(i)
            device_name = device_info['name'].lower()
            channels = device_info['maxInputChannels']
            
            logger.debug(f"Device {i}: {device_info['name']} (Input channels: {channels})")
            
            # Match device name
            if self.device_name in device_name and channels > 0:
                logger.info(f"Found device: {device_info['name']} (Index: {i})")
                self.device_index = i
                return True
        
        logger.warning(f"Device '{self.device_name}' not found, using default")
        self.device_index = None  # Use default device
        return False
    
    def open_stream(self):
        """Open audio stream"""
        logger.info("Opening audio stream...")
        
        try:
            self.stream = self.p.open(
                format=self.format,
                channels=self.channels,
                rate=self.sample_rate,
                input=True,
                frames_per_buffer=self.chunk_size,
                input_device_index=self.device_index
            )
            logger.info("Audio stream opened successfully")
            return True
        except Exception as e:
            logger.error(f"Error opening audio stream: {e}")
            return False
    
    def record(self):
        """Record audio for specified duration"""
        if not self.stream:
            logger.error("Stream not initialized. Call open_stream() first.")
            return False
        
        logger.info(f"Recording for {self.duration} seconds...")
        frames = []
        
        try:
            # Calculate total frames to record
            total_frames = int(self.sample_rate / self.chunk_size * self.duration)
            start_time = time.time()
            
            print("\n")  # Space for progress bar
            
            # Record frames
            for i in range(total_frames):
                try:
                    data = self.stream.read(self.chunk_size, exception_on_overflow=False)
                    frames.append(data)
                    
                    # Show progress only every ~5 updates (less overhead)
                    if (i + 1) % max(1, total_frames // 5) == 0:
                        elapsed = time.time() - start_time
                        bar_length = 40
                        progress = min(int(bar_length * (i + 1) / total_frames), bar_length)
                        bar = '█' * progress + '░' * (bar_length - progress)
                        percent = min(int(100 * (i + 1) / total_frames), 100)
                        
                        # Use \r to overwrite the same line
                        print(f'\r[{bar}] {percent}% ({elapsed:.1f}s/{self.duration}s)', end='', flush=True)
                    
                except Exception as e:
                    logger.error(f"Error reading audio frame: {e}")
                    continue
            
            actual_duration = time.time() - start_time
            print(f'\r[{"█" * 40}] 100% ({actual_duration:.1f}s/{self.duration}s)')
            logger.info(f"Recording complete. Captured {len(frames)} frames in {actual_duration:.2f}s")
            return frames
        
        except KeyboardInterrupt:
            logger.warning("Recording interrupted by user")
            return None
    
    def save_wav(self, frames):
        """Save recorded frames to WAV file"""
        if not frames:
            logger.error("No frames to save")
            return False
        
        try:
            logger.info(f"Saving audio to {self.output_file}...")
            
            with wave.open(self.output_file, 'wb') as wav_file:
                wav_file.setnchannels(self.channels)
                wav_file.setsampwidth(self.p.get_sample_size(self.format))
                wav_file.setframerate(self.sample_rate)
                
                # Write all frames
                for frame in frames:
                    wav_file.writeframes(frame)
            
            file_size = Path(self.output_file).stat().st_size
            logger.info(f"Successfully saved {file_size} bytes to {self.output_file}")
            return True
        
        except Exception as e:
            logger.error(f"Error saving WAV file: {e}")
            return False
    
    def cleanup(self):
        """Clean up resources"""
        logger.info("Cleaning up resources...")
        
        if self.stream:
            try:
                self.stream.stop_stream()
                self.stream.close()
            except Exception as e:
                logger.error(f"Error closing stream: {e}")
        
        if self.p:
            try:
                self.p.terminate()
            except Exception as e:
                logger.error(f"Error terminating PyAudio: {e}")
    
    def run(self):
        """Run the recorder"""
        try:
            # Find device
            self.find_device()
            
            # Open stream
            if not self.open_stream():
                logger.error("Failed to open audio stream")
                return False
            
            # Record audio
            frames = self.record()
            if frames is None:
                logger.warning("Recording was cancelled")
                return False
            
            # Save to file
            if not self.save_wav(frames):
                logger.error("Failed to save audio file")
                return False
            
            logger.info("Recording completed successfully!")
            return True
        
        except Exception as e:
            logger.error(f"Unexpected error: {e}", exc_info=True)
            return False
        
        finally:
            self.cleanup()


def list_devices():
    """List all available audio devices"""
    p = pyaudio.PyAudio()
    device_count = p.get_device_count()
    default_device = p.get_default_input_device_info()
    default_index = default_device['index'] if default_device else -1
    
    print(f"\nFound {device_count} audio devices:\n")
    for i in range(device_count):
        device_info = p.get_device_info_by_index(i)
        channels = device_info['maxInputChannels']
        
        # Skip devices with no input channels
        if channels == 0:
            continue
            
        print(f"Device {i}:")
        print(f"  Name: {device_info['name']}")
        print(f"  Input Channels: {channels}")
        print(f"  Sample Rate: {int(device_info['defaultSampleRate'])} Hz")
        print(f"  Default: {'Yes' if i == default_index else 'No'}")
        print()
    
    p.terminate()


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description='Record ReSpeaker microphone for a specified duration'
    )
    parser.add_argument(
        '--duration',
        type=int,
        default=10,
        help='Recording duration in seconds (default: 10)'
    )
    parser.add_argument(
        '--device',
        type=str,
        default='reachy',
        help='Audio device name (default: respeaker)'
    )
    parser.add_argument(
        '--output',
        type=str,
        default='recording.wav',
        help='Output WAV file path (default: recording.wav)'
    )
    parser.add_argument(
        '--list-devices',
        action='store_true',
        help='List all available audio devices and exit'
    )
    
    args = parser.parse_args()
    
    # List devices if requested
    if args.list_devices:
        list_devices()
        sys.exit(0)
    
    # Validate arguments
    if args.duration <= 0:
        logger.error("Duration must be positive")
        sys.exit(1)
    
    # Create and run recorder
    recorder = ReSpeakerRecorder(
        device_name=args.device,
        duration=args.duration,
        output_file=args.output
    )
    
    success = recorder.run()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
