import logging
from pathlib import Path
from typing import Dict

logger = logging.getLogger(__name__)

def get_agent_prompts(agent_name: str) -> Dict[str, str]:
    """
    Retrieve prompts for a given agent.
    
    Args:
        agent_name: The directory name of the agent (e.g., 'entity_agent').
        
    Returns:
        Dictionary containing 'system' and 'user' prompts if found.
    """
    base_path = Path(__file__).parent
    agent_dir = base_path / agent_name
    
    if not agent_dir.exists() or not agent_dir.is_dir():
        logger.warning(f"Agent directory not found: {agent_dir}")
        return {}
        
    prompts = {}
    
    # Try different naming conventions if needed, but per plan:
    # {agent_name}.system.md and {agent_name}.user.md
    
    system_path = agent_dir / f"{agent_name}.system.md"
    if system_path.exists():
        prompts["system"] = system_path.read_text().strip()
    else:
        logger.warning(f"System prompt not found at {system_path}")
        
    user_path = agent_dir / f"{agent_name}.user.md"
    if user_path.exists():
        prompts["user"] = user_path.read_text().strip()
    else:
        logger.warning(f"User prompt not found at {user_path}")
        
    return prompts
