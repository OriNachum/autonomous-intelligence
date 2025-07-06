#!/usr/bin/env python3
"""
Gemma - Multimodal AI Assistant
Run script for easy startup
"""

import sys
import os
import asyncio

# Add src directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from src.gemma import main

if __name__ == "__main__":
    print("Starting Gemma Multimodal AI Assistant...")
    asyncio.run(main())