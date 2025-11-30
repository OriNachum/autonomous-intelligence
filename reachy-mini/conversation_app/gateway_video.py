#!/usr/bin/env python3
"""
Gateway Video - Video processing component for Reachy Gateway
Adapted from standard GStreamer WebRTC consumer example.
"""

import os
import time
import logging
import asyncio
from pathlib import Path
from collections import deque
from typing import Optional, Callable
import numpy as np
from concurrent.futures import ProcessPoolExecutor

from .logger import get_logger
logger = logging.getLogger(__name__)

# --- CONFIGURATION ---
# Since you are using network_mode: host, 127.0.0.1 is correct
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8443
PEER_NAME = "reachymini"

# --- CHECK DEPENDENCIES ---
try:
    import gi
    gi.require_version("Gst", "1.0")
    from gi.repository import GLib, Gst
    HAS_GST = True
except ImportError:
    HAS_GST = False
    logger.warning("PyGObject (gi) not available")

try:
    import cv2
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False


# --- ISOLATED TASK ---
# We MUST keep this outside the class. 
# 'find_producer_peer_id_by_name' creates its own event loop. 
# If we run it directly inside GatewayVideo (which is already async), it will crash.
def fetch_peer_id_task(host, port, peer_name):
    from gst_signalling.utils import find_producer_peer_id_by_name
    # Connect and fetch ID exactly like the source of truth
    return find_producer_peer_id_by_name(host, port, peer_name)
# ---------------------


class GatewayVideo:
    """
    Video consumer adapted from GstConsumer example.
    Captures frames via appsink instead of displaying them.
    """
    
    def __init__(self, event_callback: Callable, frame_interval: int = 100):
        logger.info("Initializing Gateway Video")
        
        self.emit_event = event_callback
        self.frame_interval = frame_interval
        
        self.signalling_host = os.getenv('REACHY_HOST', DEFAULT_HOST)
        self.signalling_port = int(os.getenv('REACHY_SIGNALLING_PORT', str(DEFAULT_PORT)))
        self.peer_name = os.getenv('REACHY_PEER_NAME', PEER_NAME)
        
        self.videos_dir = os.getenv('VIDEOS_DIR', './videos')
        os.makedirs(self.videos_dir, exist_ok=True)
        
        self.max_videos = int(os.getenv('MAX_VIDEOS', '20'))
        self.video_files = deque(maxlen=self.max_videos)
        
        self.frame_count = 0
        self.saved_frame_count = 0
        self.shutdown_requested = False
        
        # GStreamer objects
        self.pipeline = None
        self.source = None
        self.appsink = None
        self.bus = None

    async def start(self):
        """
        Equivalent to the __init__ logic of GstConsumer, 
        but executed asynchronously to fit the gateway app.
        """
        logger.info(f"Starting Video Gateway (Target: {self.signalling_host}:{self.signalling_port})")

        # 1. FETCH PEER ID
        # We use a process executor to prevent "Event loop already running" error
        loop = asyncio.get_running_loop()
        try:
            with ProcessPoolExecutor(max_workers=1) as pool:
                peer_id = await loop.run_in_executor(
                    pool, 
                    fetch_peer_id_task, 
                    self.signalling_host, 
                    self.signalling_port, 
                    self.peer_name
                )
            logger.info(f"Found peer id: {peer_id}")
        except Exception as e:
            logger.error(f"Failed to find peer ID: {e}")
            return # Stop here if we can't find peer

        # 2. INITIALIZE GSTREAMER
        if not Gst.is_initialized():
            Gst.init(None)

        # 3. BUILD PIPELINE (Matches Source of Truth)
        self.pipeline = Gst.Pipeline.new("webRTC-consumer")
        self.source = Gst.ElementFactory.make("webrtcsrc")

        if not self.pipeline or not self.source:
            logger.error("Failed to create pipeline or webrtcsrc")
            return

        self.pipeline.add(self.source)

        # 4. CONNECT SIGNALS (Matches Source of Truth)
        self.source.connect("pad-added", self._on_pad_added)
        
        signaller = self.source.get_property("signaller")
        signaller.set_property("producer-peer-id", peer_id)
        signaller.set_property("uri", f"ws://{self.signalling_host}:{self.signalling_port}")

        # 5. PLAY
        logger.info("Setting pipeline state to PLAYING...")
        ret = self.pipeline.set_state(Gst.State.PLAYING)
        if ret == Gst.StateChangeReturn.FAILURE:
            logger.error("Error starting playback")
            return
        
        self.bus = self.pipeline.get_bus()
        logger.info("Video pipeline started successfully")

    def _configure_webrtcbin(self, webrtcsrc: Gst.Element) -> None:
        """Exact copy of helper from source of truth"""
        if isinstance(webrtcsrc, Gst.Bin):
            webrtcbin_name = "webrtcbin0"
            webrtcbin = webrtcsrc.get_by_name(webrtcbin_name)
            if webrtcbin is not None:
                # jitterbuffer has a default 200 ms buffer.
                webrtcbin.set_property("latency", 50)

    def _on_pad_added(self, webrtcsrc: Gst.Element, pad: Gst.Pad) -> None:
        """
        Adapted from webrtcsrc_pad_added_cb.
        Instead of fpsdisplaysink (GUI), we use appsink (Data Processing).
        """
        self._configure_webrtcbin(webrtcsrc)
        
        pad_name = pad.get_name()
        if pad_name.startswith("video"):
            logger.info("Video pad added, linking appsink...")
            
            # --- ADAPTATION: Use appsink instead of fpsdisplaysink ---
            self.appsink = Gst.ElementFactory.make("appsink")
            if not self.appsink:
                logger.error("Failed to create appsink")
                return
            
            # Configure appsink for frame extraction
            self.appsink.set_property("emit-signals", True)
            self.appsink.set_property("sync", False) # Process as fast as possible
            self.appsink.set_property("drop", True)  # Drop old frames if processing is slow
            self.appsink.set_property("max-buffers", 1)
            
            # Force RGB format for easy processing
            caps = Gst.Caps.from_string("video/x-raw,format=RGB")
            self.appsink.set_property("caps", caps)
            
            self.appsink.connect("new-sample", self._on_new_sample)
            
            self.pipeline.add(self.appsink)
            pad.link(self.appsink.get_static_pad("sink"))
            self.appsink.sync_state_with_parent()
            logger.info("appsink linked")

        elif pad_name.startswith("audio"):
             # We ignore audio here as gateway_audio handles it, 
             # or we can just link fakesink to keep the pipe happy.
             pass

    def _on_new_sample(self, appsink: Gst.Element) -> Gst.FlowReturn:
        """Capture frame callback"""
        self.frame_count += 1
        
        # Throttle processing
        if self.frame_count % self.frame_interval != 0:
            return Gst.FlowReturn.OK
            
        sample = appsink.emit("pull-sample")
        if not sample: return Gst.FlowReturn.OK
        
        buffer = sample.get_buffer()
        if not buffer: return Gst.FlowReturn.OK
        
        caps = sample.get_caps()
        s = caps.get_structure(0)
        w, h = s.get_value("width"), s.get_value("height")
        
        success, map_info = buffer.map(Gst.MapFlags.READ)
        if not success: return Gst.FlowReturn.OK
        
        try:
            # Create numpy array
            frame_data = np.ndarray(shape=(h, w, 3), dtype=np.uint8, buffer=map_info.data)
            # Save asynchronously
            asyncio.create_task(self._save_frame(frame_data.copy()))
        finally:
            buffer.unmap(map_info)
            
        return Gst.FlowReturn.OK

    async def _save_frame(self, frame: np.ndarray):
        """Save frame to disk (async to not block loop)"""
        try:
            timestamp = int(time.time() * 1000)
            filename = os.path.join(self.videos_dir, f"frame_{timestamp}.jpg")
            
            if HAS_CV2:
                # Convert RGB to BGR for OpenCV
                frame_bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
                await asyncio.to_thread(cv2.imwrite, filename, frame_bgr)
            else:
                from PIL import Image
                img = Image.fromarray(frame, mode='RGB')
                await asyncio.to_thread(img.save, filename)
            
            self.saved_frame_count += 1
            
            # Cleanup old files
            if len(self.video_files) >= self.max_videos:
                old = self.video_files.popleft()
                if os.path.exists(old):
                    await asyncio.to_thread(os.remove, old)
            self.video_files.append(filename)
            
            # Emit
            await self.emit_event("video_frame_captured", {
                "file_path": filename,
                "timestamp": timestamp
            })
        except Exception as e:
            logger.error(f"Save frame error: {e}")

    # --- MESSAGE LOOP ---
    # In the source of truth, this is the 'while True' loop.
    # Here, we run it as an async task.
    async def run_gst_loop(self):
        logger.info("Starting GStreamer message loop")
        while not self.shutdown_requested:
            if self.bus:
                msg = self.bus.timed_pop_filtered(10 * Gst.MSECOND, Gst.MessageType.ANY)
                if msg:
                    if msg.type == Gst.MessageType.ERROR:
                        err, debug = msg.parse_error()
                        logger.error(f"GStreamer Error: {err}, {debug}")
                    elif msg.type == Gst.MessageType.EOS:
                        logger.info("End-Of-Stream")
                        break
            else:
                logger.warning("GStreamer bus not initialized")
            await asyncio.sleep(0.01)

    def stop(self):
        self.shutdown_requested = True
        if self.pipeline:
            self.pipeline.send_event(Gst.Event.new_eos())
            self.pipeline.set_state(Gst.State.NULL)
            
    def cleanup(self):
        self.stop()