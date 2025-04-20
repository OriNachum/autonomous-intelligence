"""
Handler for executing tool calls from the LLM.
"""
import json
import os
from pathlib import Path
from config import logger

def handle_tool_call(function_name, arguments, request_id):
    """
    Execute a tool call based on the function name and arguments.
    
    Args:
        function_name (str): The name of the function to execute
        arguments (str): The JSON string containing the function arguments
        request_id (str): A unique identifier for the request
        
    Returns:
        dict: The result of the tool execution
    """
    logger.info(f"[{request_id}] Executing tool call: {function_name}")
    
    # Parse the arguments
    try:
        args = json.loads(arguments)
        logger.info(f"[{request_id}] Tool arguments: {args}")
    except json.JSONDecodeError:
        logger.error(f"[{request_id}] Failed to parse tool arguments: {arguments}")
        return {"error": "Invalid arguments format"}
    
    # Dispatch to the appropriate function handler
    if function_name == "apply_patch":
        return handle_apply_patch(args, request_id)
    else:
        logger.warning(f"[{request_id}] Unknown tool: {function_name}")
        return {"error": f"Unknown tool: {function_name}"}

def handle_apply_patch(args, request_id):
    """
    Handle apply_patch tool call to create or update files.
    
    Args:
        args (dict): The parsed arguments for the apply_patch function
        request_id (str): A unique identifier for the request
        
    Returns:
        dict: The result of applying the patch
    """
    # Get the content from the arguments
    content = args.get("$$")
    if not content:
        logger.error(f"[{request_id}] Missing content in apply_patch arguments")
        return {"error": "Missing content"}
    
    # Extract the file path from the content
    # Looking for patterns like "Save the following content to demo.md:"
    import re
    file_path_match = re.search(r"Save the following content to ([^\s:]+):", content)
    if file_path_match:
        file_name = file_path_match.group(1)
        # Clean up the file path
        file_name = file_name.strip()
        # Determine the content to write
        lines = content.splitlines()
        
        # Find where the actual content starts (after the instruction line)
        start_idx = None
        for i, line in enumerate(lines):
            if file_name in line and "Save" in line:
                start_idx = i
                break
        
        if start_idx is not None:
            # Get the content after the instruction line, allowing for blank lines
            file_content = "\n".join(lines[start_idx + 1:]).strip()
            
            # Create the absolute path
            # For safety, we'll put all created files in the workspace directory
            workspace_dir = Path(os.environ.get("WORKSPACE_DIR", "/home/orin/git/autonomous-intelligence/baby-tau/workspace"))
            abs_file_path = workspace_dir / file_name
            
            # Ensure the directory exists
            os.makedirs(os.path.dirname(abs_file_path), exist_ok=True)
            
            # Write the file
            try:
                with open(abs_file_path, 'w') as f:
                    f.write(file_content)
                logger.info(f"[{request_id}] Successfully wrote file: {abs_file_path}")
                return {
                    "success": True,
                    "message": f"File {file_name} created successfully",
                    "path": str(abs_file_path)
                }
            except Exception as e:
                logger.error(f"[{request_id}] Error writing file: {str(e)}")
                return {"error": f"Failed to write file: {str(e)}"}
        else:
            logger.error(f"[{request_id}] Could not find file path in content")
            
    # If we couldn't extract a path or if there was another issue, 
    # create a default file with the content
    try:
        workspace_dir = Path(os.environ.get("WORKSPACE_DIR", "/home/orin/git/autonomous-intelligence/baby-tau/workspace"))
        default_path = workspace_dir / "demo.md"
        
        with open(default_path, 'w') as f:
            f.write(content)
            
        logger.info(f"[{request_id}] Wrote content to default file: {default_path}")
        return {
            "success": True,
            "message": f"Content written to default file at {default_path}",
            "path": str(default_path)
        }
    except Exception as e:
        logger.error(f"[{request_id}] Error writing default file: {str(e)}")
        return {"error": f"Failed to write default file: {str(e)}"}