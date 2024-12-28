import os
import logging
from dotenv import load_dotenv

# Set up logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

logger.info("Starting Tau application")

# Load environment variables
load_dotenv()
logger.debug("Environment variables loaded")

# API Key and other configurations
API_KEY = os.getenv("ANTHROPIC_API_KEY")
HISTORY_FILE = "conversation_history.txt"
SYSTEM_PROMPT_FILE = "prompts/system.md"

if not API_KEY:
    logger.error("ANTHROPIC_API_KEY environment variable is not set.")
    raise ValueError("ANTHROPIC_API_KEY environment variable is not set.")
