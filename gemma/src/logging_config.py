"""Logging configuration for Gemma"""

import logging
import sys
from typing import Optional

def setup_logging(level: str = "INFO", format_str: Optional[str] = None) -> logging.Logger:
    """Set up logging configuration"""
    
    if format_str is None:
        format_str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    
    # Configure root logger
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format=format_str,
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler("gemma.log")
        ]
    )
    
    return logging.getLogger("gemma")