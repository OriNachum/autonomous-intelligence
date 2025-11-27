#!/usr/bin/env python3
"""
Gateway Video - Video processing component for Reachy Gateway

This module handles:
1. Video capture from Reachy's WebRTC camera stream
2. Frame extraction every nth frame (default: 100)
3. Frame saving to disk (/videos directory)
4. Event emission for captured frames
"""

import os
import time
import logging
import asyncio
from pathlib import Path
from collections import deque
from typing import Optional, Callable
import numpy as np

# Try to import gi (GStreamer) - required for video capture
try:
    import gi
    from gst_signalling.utils import find_producer_peer_id_by_name
    gi.require_version("Gst", "1.0")
    from gi.repository import GLib, Gst
    HAS_GST = True
except ImportError:
    HAS_GST = False
    logger.warning("PyGObject (gi) not available - video capture will be disabled")

# Try to import cv2, fallback to PIL if not available
try:
    import cv2
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False

logger = logging.getLogger(__name__)


class GatewayVideo:
    """Video processing component for gateway service"""
    
    def __init__(self, event_callback: Callable, frame_interval: int = 100):
        """
        Initialize the video gateway.
        
        Args:
            event_callback: Async callback function for emitting events: async def callback(event_type, data)
            frame_interval: Capture and save every nth frame (default: 100)
        """
        logger.info("Initializing Gateway Video")
        
        # Check if GST dependencies are available
        if not HAS_GST:
            raise ImportError(
                "PyGObject (gi) is required for video capture but not installed. "
                "Set ENABLE_VISION=false to disable video processing."
            )
        
        self.emit_event = event_callback
        self.frame_interval = frame_interval
        
        # Configuration from environment
        self.signalling_host = os.getenv('REACHY_HOST', '127.0.0.1')
        self.signalling_port = int(os.getenv('REACHY_SIGNALLING_PORT', '8443'))
        self.peer_name = os.getenv('REACHY_PEER_NAME', 'reachymini')
        
        # Videos directory
        self.videos_dir = os.getenv('VIDEOS_DIR', './videos')
        os.makedirs(self.videos_dir, exist_ok=True)
        logger.info(f"Videos will be saved to: {self.videos_dir}")
        
        # Rolling list of last N video files
        self.max_videos = int(os.getenv('MAX_VIDEOS', '20'))
        self.video_files = deque(maxlen=self.max_videos)
        
        # Frame counting
        self.frame_count = 0
        self.saved_frame_count = 0
        
        # GStreamer components
        self.pipeline = None
        self.source = None
        self.appsink = None
        self.bus = None
        
        # Shutdown flag
        self.shutdown_requested = False
        
        # GStreamer loop thread
        self.gst_loop = None
        self.gst_thread = None
        
        logger.info("Gateway Video initialization complete")
    
    def _init_gstreamer(self):
        """Initialize GStreamer pipeline for WebRTC video capture"""
        logger.info("Initializing GStreamer pipeline for video capture")
        
        # Initialize GStreamer
        Gst.init(None)
        
        # Create pipeline
        self.pipeline = Gst.Pipeline.new("webRTC-video-consumer")
        self.source = Gst.ElementFactory.make("webrtcsrc")
        
        if not self.pipeline:
            raise RuntimeError("Pipeline could not be created")
        
        if not self.source:
            raise RuntimeError(
                "webrtcsrc component could not be created. Please make sure that the plugin is installed "
                "(see https://gitlab.freedesktop.org/gstreamer/gst-plugins-rs/-/tree/main/net/webrtc)"
            )
        
        self.pipeline.add(self.source)
        
        # Find peer ID
        peer_id = find_producer_peer_id_by_name(
            self.signalling_host, self.signalling_port, self.peer_name
        )
        logger.info(f"Found peer id: {peer_id}")
        
        # Configure source
        self.source.connect("pad-added", self._on_pad_added)
        signaller = self.source.get_property("signaller")
        signaller.set_property("producer-peer-id", peer_id)
        signaller.set_property("uri", f"ws://{self.signalling_host}:{self.signalling_port}")
        
        # Get bus for message processing
        self.bus = self.pipeline.get_bus()
        
        logger.info("GStreamer pipeline initialized")
    
    def _configure_webrtcbin(self, webrtcsrc: Gst.Element) -> None:
        """Configure webrtcbin for low latency"""
        if isinstance(webrtcsrc, Gst.Bin):
            webrtcbin_name = "webrtcbin0"
            webrtcbin = webrtcsrc.get_by_name(webrtcbin_name)
            if webrtcbin is not None:
                # Set low latency (jitterbuffer has a default 200 ms buffer)
                webrtcbin.set_property("latency", 50)
    
    def _on_pad_added(self, webrtcsrc: Gst.Element, pad: Gst.Pad) -> None:
        """Callback when a new pad is added to webrtcsrc"""
        self._configure_webrtcbin(webrtcsrc)
        
        if pad.get_name().startswith("video"):
            logger.info("Video pad added, creating appsink")
            
            # Create appsink to capture frames
            self.appsink = Gst.ElementFactory.make("appsink")
            if not self.appsink:
                logger.error("Failed to create appsink")
                return
            
            # Configure appsink
            self.appsink.set_property("emit-signals", True)
            self.appsink.set_property("sync", False)
            self.appsink.set_property("drop", True)
            self.appsink.set_property("max-buffers", 1)
            
            # Set caps for RGB format
            caps = Gst.Caps.from_string("video/x-raw,format=RGB")
            self.appsink.set_property("caps", caps)
            
            # Connect to new-sample signal
            self.appsink.connect("new-sample", self._on_new_sample)
            
            # Add to pipeline and link
            self.pipeline.add(self.appsink)
            pad.link(self.appsink.get_static_pad("sink"))
            self.appsink.sync_state_with_parent()
            
            logger.info("appsink configured and linked to video pad")
    
    def _on_new_sample(self, appsink: Gst.Element) -> Gst.FlowReturn:
        """Callback when a new video sample is available"""
        # Increment frame count
        self.frame_count += 1
        
        # Only process every nth frame
        if self.frame_count % self.frame_interval != 0:
            return Gst.FlowReturn.OK
        
        # Pull sample
        sample = appsink.emit("pull-sample")
        if sample is None:
            return Gst.FlowReturn.OK
        
        # Get buffer
        buffer = sample.get_buffer()
        if buffer is None:
            return Gst.FlowReturn.OK
        
        # Get caps to determine frame dimensions
        caps = sample.get_caps()
        struct = caps.get_structure(0)
        width = struct.get_value("width")
        height = struct.get_value("height")
        
        # Map buffer to read data
        success, map_info = buffer.map(Gst.MapFlags.READ)
        if not success:
            logger.warning("Failed to map buffer")
            return Gst.FlowReturn.OK
        
        try:
            # Convert buffer to numpy array (RGB format)
            frame_data = np.ndarray(
                shape=(height, width, 3),
                dtype=np.uint8,
                buffer=map_info.data
            )
            
            # Save frame asynchronously
            asyncio.create_task(self._save_frame(frame_data.copy()))
            
        finally:
            buffer.unmap(map_info)
        
        return Gst.FlowReturn.OK
    
    async def _save_frame(self, frame: np.ndarray):
        """
        Save frame to disk and emit event.
        
        Args:
            frame: Frame data as numpy array (RGB format)
        """
        try:
            # Generate filename
            timestamp = int(time.time() * 1000)  # milliseconds
            filename = os.path.join(self.videos_dir, f"frame_{timestamp}.jpg")
            
            # Save frame to disk
            if HAS_CV2:
                # OpenCV expects BGR, convert from RGB
                frame_bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
                await asyncio.to_thread(cv2.imwrite, filename, frame_bgr)
            else:
                # Use PIL
                from PIL import Image
                img = Image.fromarray(frame, mode='RGB')
                await asyncio.to_thread(img.save, filename)
            
            self.saved_frame_count += 1
            logger.info(f"Saved frame #{self.saved_frame_count} to {filename}")
            
            # Manage rolling list of video files
            if len(self.video_files) >= self.max_videos:
                # Remove and delete the oldest file
                oldest_file = self.video_files[0]
                if os.path.exists(oldest_file):
                    await asyncio.to_thread(os.remove, oldest_file)
                    logger.debug(f"Deleted oldest frame: {oldest_file}")
            
            # Add new file to the list
            self.video_files.append(filename)
            
            # Emit event
            await self.emit_event("video_frame_captured", {
                "frame_number": self.saved_frame_count,
                "total_frames": self.frame_count,
                "file_path": filename,
                "timestamp": timestamp
            })
            
        except Exception as e:
            logger.error(f"Error saving frame: {e}", exc_info=True)
    
    def _process_bus_messages(self) -> bool:
        """Process messages from the GStreamer bus"""
        if self.shutdown_requested:
            return False
        
        msg = self.bus.timed_pop_filtered(10 * Gst.MSECOND, Gst.MessageType.ANY)
        if msg:
            if msg.type == Gst.MessageType.ERROR:
                err, debug = msg.parse_error()
                logger.error(f"GStreamer error: {err}, {debug}")
                return False
            elif msg.type == Gst.MessageType.EOS:
                logger.info("End-Of-Stream reached")
                return False
            elif msg.type == Gst.MessageType.LATENCY:
                if self.pipeline:
                    try:
                        self.pipeline.recalculate_latency()
                    except Exception as e:
                        logger.warning(f"Failed to recalculate latency: {e}")
        
        return True
    
    def start(self):
        """Start video capture"""
        logger.info("Starting video capture")
        
        # Initialize GStreamer
        self._init_gstreamer()
        
        # Start pipeline
        ret = self.pipeline.set_state(Gst.State.PLAYING)
        if ret == Gst.StateChangeReturn.FAILURE:
            raise RuntimeError("Failed to start video pipeline")
        
        logger.info("Video pipeline started, capturing frames...")
    
    async def run_gst_loop(self):
        """Run GStreamer message processing loop"""
        logger.info("Starting GStreamer message loop")
        
        while not self.shutdown_requested:
            try:
                # Process bus messages
                if not await asyncio.to_thread(self._process_bus_messages):
                    logger.warning("GStreamer bus processing returned False")
                    break
                
                # Small sleep to prevent busy loop
                await asyncio.sleep(0.01)
            except Exception as e:
                if not self.shutdown_requested:
                    logger.error(f"Error in GStreamer loop: {e}", exc_info=True)
                await asyncio.sleep(1)
        
        logger.info("GStreamer message loop stopped")
    
    def stop(self):
        """Stop video capture"""
        logger.info("Stopping video capture")
        
        self.shutdown_requested = True
        
        if self.pipeline:
            self.pipeline.send_event(Gst.Event.new_eos())
            self.pipeline.set_state(Gst.State.NULL)
        
        logger.info("Video capture stopped")
    
    def cleanup(self):
        """Clean up resources"""
        logger.info("Cleaning up Gateway Video resources")
        
        self.stop()
        
        # Deinit GStreamer
        if self.pipeline:
            Gst.deinit()
        
        logger.info("Gateway Video cleanup complete")
